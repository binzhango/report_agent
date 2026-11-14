"""Typed runtime parameters shared by chat, CLI, and saved reports."""

import math
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from report_agent.errors import ReportError


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Parameter(StrictModel):
    type: Literal["string", "integer", "number", "boolean", "date"] = "string"
    description: str = ""
    required: bool = True
    default: str | int | float | bool | None = None
    choices: list[str | int | float | bool] = Field(default_factory=list)

    def validate_value(self, value):
        if self.type == "date":
            if not isinstance(value, str):
                raise ReportError(
                    "Use an ISO date string: YYYY-MM-DD.", code="invalid_date"
                )
            try:
                parsed = date.fromisoformat(value)
            except ValueError as exc:
                raise ReportError(
                    "Use an ISO date string: YYYY-MM-DD.", code="invalid_date"
                ) from exc
            if parsed.isoformat() != value:
                raise ReportError(
                    "Use an ISO date string: YYYY-MM-DD.", code="invalid_date"
                )
        elif self.type == "string":
            if not isinstance(value, str) or not value.strip():
                raise ReportError(
                    "Expected a non-empty string.", code="invalid_parameter"
                )
        elif self.type == "boolean":
            if type(value) is not bool:
                raise ReportError("Expected a boolean.", code="invalid_parameter")
        elif self.type == "integer":
            if type(value) is not int:
                raise ReportError("Expected an integer.", code="invalid_parameter")
        elif type(value) not in (int, float) or not math.isfinite(value):
            raise ReportError("Expected a finite number.", code="invalid_parameter")
        if self.choices and value not in self.choices:
            raise ReportError(
                "Choose one of this parameter's declared choices.",
                code="invalid_choice",
            )
        return value

    @model_validator(mode="after")
    def check_defaults(self):
        if self.default is not None:
            self.validate_value(self.default)
        for value in self.choices:
            self.validate_value(value)
        return self


class ParameterOrder(StrictModel):
    before: str
    after: str


class DateRange(StrictModel):
    """Names of saved date parameters and their calendar-month boundary rule."""

    start: str = Field(description="Name of the inclusive start date parameter.")
    end: str = Field(description="Name of the end date parameter.")
    end_inclusive: bool = False


def resolve_parameters(definitions, supplied, rules=()):
    if not isinstance(supplied, dict):
        raise ReportError(
            "Parameter values must be a mapping.", code="invalid_parameters"
        )
    unknown = supplied.keys() - definitions.keys()
    if unknown:
        raise ReportError(
            "Unknown parameters. Use only names declared in the report.",
            code="unknown_parameters",
        )
    result = {}
    for name, definition in definitions.items():
        value = supplied.get(name, definition.default)
        if value is None:
            if definition.required:
                raise ReportError(
                    f"Missing parameter: {name}", code="missing_parameter"
                )
            continue
        try:
            result[name] = definition.validate_value(value)
        except ReportError as exc:
            raise ReportError(f"{name}: {exc}", code=exc.code) from exc
    for rule in rules:
        if rule.before in result and rule.after in result:
            if result[rule.before] >= result[rule.after]:
                raise ReportError(
                    f"{rule.before} must be before {rule.after}.",
                    code="parameter_order",
                )
    return result
