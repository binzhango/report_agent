"""Persisted configuration linking layouts, parameters, and data bindings."""

from string import Formatter
from typing import Literal

from pydantic import Field, model_validator

from report_agent.authoring.models import Layout
from report_agent.definitions.parameters import Parameter, ParameterOrder, StrictModel


class FileFilter(StrictModel):
    column: str = Field(min_length=1)
    op: Literal["eq", "ge", "gt", "le", "lt"] = "eq"
    type: Literal["value", "date"] = "value"


class QueryBinding(StrictModel):
    connection: str = Field(min_length=1)
    query: str = Field(min_length=1)
    parameter_bindings: dict[str, str] = Field(default_factory=dict)
    row_limit: int = Field(default=1000, ge=1, le=100000)
    columns: list[str] = Field(default_factory=list)
    filters: dict[str, FileFilter] = Field(default_factory=dict)


class Chart(StrictModel):
    table: str
    x: str
    y: str
    kind: Literal["bar", "line"] = "bar"


class ReportDefinition(StrictModel):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    layout: Layout
    parameters: dict[str, Parameter] = Field(default_factory=dict)
    parameter_order: list[ParameterOrder] = Field(default_factory=list)
    queries: dict[str, QueryBinding] = Field(default_factory=dict)
    text_bindings: dict[str, str] = Field(default_factory=dict)
    charts: dict[str, Chart] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_bindings(self):
        import re

        if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", n) for n in self.parameters):
            raise ValueError("Parameter names must be simple identifiers.")
        blocks = {b.name: b for b in self.layout.blocks}
        for name, query in self.queries.items():
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
                raise ValueError("Query names must be simple identifiers.")
            if name in blocks and blocks[name].kind != "table":
                raise ValueError(f"Query {name} conflicts with a non-table block.")
            if set(query.parameter_bindings.values()) - self.parameters.keys():
                raise ValueError(f"Query {name} references undeclared parameters.")
        for name, chart in self.charts.items():
            if name not in blocks or blocks[name].kind != "chart":
                raise ValueError("Chart binding must name a chart block.")
            if chart.table not in self.queries:
                raise ValueError("Charts require a declared table query.")
        for block in blocks.values():
            if block.kind == "table" and block.name not in self.queries:
                raise ValueError(f"Missing query for table {block.name}.")
            if block.kind == "chart" and block.name not in self.charts:
                raise ValueError(f"Missing binding for chart {block.name}.")
        for name, template in self.text_bindings.items():
            if name != "title" and (name not in blocks or blocks[name].kind != "text"):
                raise ValueError("Text binding must name title or a text block.")
            for _, field, spec, conversion in Formatter().parse(template):
                if field is not None and (
                    field not in self.parameters or spec or conversion
                ):
                    raise ValueError("Use only simple {parameter} text bindings.")
        for rule in self.parameter_order:
            if rule.before not in self.parameters or rule.after not in self.parameters:
                raise ValueError("Parameter order references unknown parameters.")
            first, second = self.parameters[rule.before], self.parameters[rule.after]
            if first.type != second.type or first.type not in {
                "date",
                "integer",
                "number",
            }:
                raise ValueError(
                    f"Order rule {rule.before} < {rule.after} has types "
                    f"{first.type}/{second.type}. Use matching date/numeric types; "
                    "for a date range set both parameters' type to date."
                )
        return self
