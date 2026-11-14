"""Resolve tables before dependent agent text, then supply normal render inputs."""

import json
import logging
from collections.abc import Mapping
from dataclasses import replace
from math import isfinite
from pathlib import Path

import pandas as pd

from report_agent.metadata.models import InputDefinition, TemplateMetadata
from report_agent.metadata.office import (
    ExportOptions,
    OfficeInputDefinition,
    OfficeMetadata,
)
from report_agent.models.inputs import ContentInput, TableInput, TextInput
from report_agent.models.results import Diagnostic
from report_agent.resolution.interfaces import AgentTextGenerator, DataSource
from report_agent.resolution.models import (
    ColumnSummary,
    GenerationRequest,
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
        animation_generators=None,
        summary_max_columns: int = 20,
        summary_max_row_chars: int = 8192,
    ) -> None:
        if summary_max_columns < 1:
            raise ValueError("summary_max_columns must be positive.")
        if summary_max_row_chars < 0:
            raise ValueError("summary_max_row_chars must be non-negative.")
        self._animation_generators = animation_generators
        self._sources = dict(sources)
        self._text_generator = text_generator
        self._summary_max_columns = summary_max_columns
        self._summary_max_row_chars = summary_max_row_chars

    def resolve(
        self,
        metadata: TemplateMetadata | OfficeMetadata,
        *,
        inputs: Mapping[str, ContentInput] | None = None,
        queries: Mapping[str, QuerySource] | None = None,
        media_workspace: Path | None = None,
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
                remaining_row_chars = self._summary_max_row_chars
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
                        value.data,
                        metadata.inputs[dependency].summary_head_rows,
                        remaining_row_chars,
                    )
                    if tables[dependency].head_rows:
                        remaining_row_chars -= len(
                            self._row_json(tables[dependency].head_rows)
                        )
                resolved[name] = self._generate(definition, tables)
            for name, definition in metadata.inputs.items():
                if definition.source != "generator" or name in resolved:
                    continue
                if self._animation_generators is None or media_workspace is None:
                    raise ValueError(
                        "Animation generation needs registry and media_workspace."
                    )
                tables = {}
                for dependency in definition.uses:
                    value = resolved.get(dependency)
                    if not isinstance(value, TableInput):
                        raise ValueError(
                            f"Animation needs resolved table {dependency!r}."
                        )
                    tables[dependency] = value.data
                resolved[name] = self._animation_generators.generate(
                    definition.generator,
                    tables,
                    definition.export or ExportOptions(),
                    media_workspace / name,
                )
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

    def _generate(
        self,
        definition: InputDefinition | OfficeInputDefinition,
        tables: Mapping[str, TableSummary],
    ) -> TextInput:
        request = GenerationRequest(definition.prompt, tables, definition.max_chars)
        for attempt in range(2):
            retry_suffix = " after 1 retry" if attempt else ""
            text = self._text_generator.generate(request)
            if not isinstance(text, str):
                raise ValueError(
                    f"Agent text generator must return plain text{retry_suffix}."
                )
            value = TextInput(text)
            issues = text_issues(value, definition)
            if not issues:
                return value
            message = "; ".join(message for _, message in issues)
            if attempt == 0 and all(code == "text_length" for code, _ in issues):
                request = replace(
                    request,
                    retry_feedback=f"{message} Previous output had {len(text)} "
                    "characters. Return a replacement within "
                    f"{request.max_chars} characters.",
                )
            else:
                raise ValueError(f"{message.rstrip('.')}{retry_suffix}.")

    def _summary(
        self, frame: pd.DataFrame, head_rows: int, max_row_chars: int
    ) -> TableSummary:
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
        rows = []
        row_chars = 2  # JSON array brackets; include separators and escaped cells.
        for row in frame.iloc[:head_rows, : len(columns)].itertuples(
            index=False, name=None
        ):
            cells = tuple(self._summary_cell(value) for value in row)
            cost = len(self._row_json(cells)) + (1 if rows else 0)
            if row_chars + cost > max_row_chars:
                break
            rows.append(cells)
            row_chars += cost
        return TableSummary(
            len(frame),
            frame.shape[1],
            tuple(columns),
            max(0, frame.shape[1] - len(columns)),
            tuple(rows),
            min(head_rows, len(frame)) - len(rows),
        )

    @staticmethod
    def _row_json(value: object) -> str:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
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
