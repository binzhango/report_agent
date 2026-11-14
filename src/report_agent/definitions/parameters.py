"""Typed runtime parameters shared by chat, CLI, and saved reports."""

import math
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
                raise ValueError("Use an ISO date string: YYYY-MM-DD.")
            parsed = date.fromisoformat(value)
            if parsed.isoformat() != value:
                raise ValueError("Use an ISO date string: YYYY-MM-DD.")
        elif self.type == "string":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Expected a non-empty string.")
        elif self.type == "boolean":
            if type(value) is not bool:
                raise ValueError("Expected a boolean.")
        elif self.type == "integer":
            if type(value) is not int:
                raise ValueError("Expected an integer.")
        elif type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("Expected a finite number.")
        if self.choices and value not in self.choices:
            raise ValueError(f"Choose one of {self.choices}.")
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


def resolve_parameters(definitions, supplied, rules=()):
    if not isinstance(supplied, dict):
        raise ValueError("Parameter values must be a mapping.")
    unknown = supplied.keys() - definitions.keys()
    if unknown:
        raise ValueError(f"Unknown parameters: {sorted(unknown)}")
    result = {}
    for name, definition in definitions.items():
        value = supplied.get(name, definition.default)
        if value is None:
            if definition.required:
                raise ValueError(f"Missing parameter: {name}")
            continue
        try:
            result[name] = definition.validate_value(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name}: {exc}") from exc
    for rule in rules:
        if rule.before in result and rule.after in result:
            if result[rule.before] >= result[rule.after]:
                raise ValueError(f"{rule.before} must be before {rule.after}.")
    return result
