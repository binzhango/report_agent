"""Resolve tables before dependent agent text, then supply normal render inputs."""

import logging
from collections.abc import Mapping
from math import isfinite

import pandas as pd

from report_agent.metadata.models import TemplateMetadata
from report_agent.models.inputs import ContentInput, TableInput, TextInput
from report_agent.models.results import Diagnostic
from report_agent.resolution.interfaces import AgentTextGenerator, DataSource
from report_agent.resolution.models import (
    ColumnSummary,
    QuerySource,
    ResolutionResult,
    TableSummary,
)
from report_agent.validation.text import text_issues

logger = logging.getLogger(__name__)


class ContentResolver:
    def __init__(
        self,
        *,
        sources: Mapping[str, DataSource],
        text_generator: AgentTextGenerator | None = None,
        summary_max_columns: int = 20,
    ) -> None:
        if summary_max_columns < 1:
            raise ValueError("summary_max_columns must be positive.")
        self._sources = dict(sources)
        self._text_generator = text_generator
        self._summary_max_columns = summary_max_columns

    def resolve(
        self,
        metadata: TemplateMetadata,
        *,
        inputs: Mapping[str, ContentInput] | None = None,
        queries: Mapping[str, QuerySource] | None = None,
    ) -> ResolutionResult:
        resolved = dict(inputs or {})
        queries = dict(queries or {})
        name = None
        try:
            unknown = (resolved.keys() | queries.keys()) - metadata.inputs.keys()
            if unknown:
                raise ValueError(f"Undeclared resolution inputs: {sorted(unknown)}")
            if resolved.keys() & queries.keys():
                raise ValueError(
                    "An input cannot have both a supplied value and a query."
                )
            for name, query in queries.items():
                if metadata.inputs[name].type != "table":
                    raise ValueError("Queries can populate only declared table inputs.")
                if query.connection not in self._sources:
                    raise ValueError(f"Unknown data source: {query.connection}")
                frame = self._sources[query.connection].fetch(query)
                if not isinstance(frame, pd.DataFrame) or frame.empty:
                    raise ValueError("Data source must return a non-empty DataFrame.")
                if len(frame) > query.row_limit:
                    raise ValueError(
                        f"Data source exceeded row limit {query.row_limit}."
                    )
                resolved[name] = TableInput(frame)
            for name, definition in metadata.inputs.items():
                if definition.source != "agent" or name in resolved:
                    continue
                if self._text_generator is None:
                    raise ValueError("Agent text requires an injected text generator.")
                tables = {}
                for dependency in definition.uses:
                    value = resolved.get(dependency)
                    if (
                        not isinstance(value, TableInput)
                        or not isinstance(value.data, pd.DataFrame)
                        or value.data.empty
                    ):
                        raise ValueError(
                            f"Agent input requires resolved table {dependency!r}."
                        )
                    tables[dependency] = self._summary(
                        value.data, metadata.inputs[dependency].summary_head_rows
                    )
                text = self._text_generator.generate(definition.prompt, tables)
                if not isinstance(text, str):
                    raise ValueError("Agent text generator must return plain text.")
                value = TextInput(text)
                issues = text_issues(value, definition)
                if issues:
                    raise ValueError("; ".join(message for _, message in issues))
                resolved[name] = value
            return ResolutionResult(resolved)
        except Exception as exc:
            code = (
                "resolution_failed"
                if isinstance(exc, (ValueError, OSError))
                else "internal_error"
            )
            if code == "internal_error":
                logger.exception(
                    "Unexpected content resolution failure for input %s", name
                )
            return ResolutionResult(
                resolved,
                (
                    Diagnostic(
                        "resolution",
                        code,
                        f"{type(exc).__name__}: {exc}",
                        input_name=name,
                    ),
                ),
            )

    def _summary(self, frame: pd.DataFrame, head_rows: int) -> TableSummary:
        columns = []
        for index in range(min(frame.shape[1], self._summary_max_columns)):
            series = frame.iloc[:, index]
            metrics = {"non_null_count": int(series.count())}
            if pd.api.types.is_numeric_dtype(
                series.dtype
            ) and not pd.api.types.is_complex_dtype(series.dtype):
                values = series.dropna()
                for metric in ("min", "max", "mean"):
                    value = getattr(values, metric)() if len(values) else None
                    value = value.item() if hasattr(value, "item") else value
                    metrics[metric] = (
                        value if value is not None and isfinite(value) else None
                    )
            columns.append(
                ColumnSummary(
                    str(frame.columns[index])[:120], str(series.dtype), metrics
                )
            )
        return TableSummary(
            len(frame),
            frame.shape[1],
            tuple(columns),
            max(0, frame.shape[1] - len(columns)),
            tuple(
                tuple(self._summary_cell(value) for value in row)
                for row in frame.iloc[:head_rows, : len(columns)].itertuples(
                    index=False, name=None
                )
            ),
        )

    @staticmethod
    def _summary_cell(value: object) -> str | int | float | bool | None:
        if value is None or value is pd.NA or value is pd.NaT:
            return None
        value = value.item() if hasattr(value, "item") else value
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value if isfinite(value) else None
        return str(value)[:200]
