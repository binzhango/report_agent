"""Contracts for optional data preparation and agent text generation."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from report_agent.models.inputs import ContentInput
from report_agent.models.results import Diagnostic


class QuerySource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    connection: str = Field(min_length=1)
    query: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    row_limit: int = Field(default=10_000, ge=1)


@dataclass(frozen=True)
class ColumnSummary:
    name: str
    dtype: str
    metrics: Mapping[str, int | float | None]


@dataclass(frozen=True)
class TableSummary:
    row_count: int
    column_count: int
    columns: tuple[ColumnSummary, ...]
    columns_omitted: int
    head_rows: tuple[tuple[str | int | float | bool | None, ...], ...] = ()


@dataclass(frozen=True)
class ResolutionResult:
    inputs: Mapping[str, ContentInput]
    diagnostics: tuple[Diagnostic, ...] = ()
