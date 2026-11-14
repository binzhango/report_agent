"""Typed chat questions shared by agent tools, Gradio, and saved report runs."""

import json
import math
from datetime import date, datetime
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from report_agent.definitions.parameters import StrictModel, resolve_parameters
from report_agent.errors import ReportError


class InputField(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
    label: str = Field(min_length=1, max_length=200)
    type: Literal[
        "text", "multiline", "date", "month", "number", "integer", "select", "boolean"
    ] = "text"
    required: bool = True
    choices: list[str] = Field(default_factory=list, max_length=40)
    default: str | int | float | bool | None = None
    placeholder: str = Field(default="", max_length=200)
    help: str = Field(default="", max_length=500)
    allow_other: bool = False

    @model_validator(mode="after")
    def valid_choices(self):
        if self.type == "select" and not self.choices:
            raise ReportError("Select fields require choices.", code="invalid_form")
        if any(not choice or len(choice) > 200 for choice in self.choices):
            raise ReportError(
                "Choices must contain 1–200 characters.", code="invalid_form"
            )
        if len(set(self.choices)) != len(self.choices) or "Other…" in self.choices:
            raise ReportError(
                "Choices must be unique; Other… is reserved.", code="invalid_form"
            )
        if self.allow_other and self.type != "select":
            raise ReportError(
                "Only select fields support allow_other.", code="invalid_form"
            )
        if self.default is not None:
            self.default = self.normalize(self.default)
        return self

    def normalize(self, value):
        if value is None or isinstance(value, str) and not value.strip():
            if self.required:
                raise ReportError(
                    f"{self.label}: enter a value.", code="required_input"
                )
            return None
        if self.type in {"text", "multiline", "select", "date", "month"}:
            if not isinstance(value, str) or len(value) > 2000:
                raise ReportError(
                    f"{self.label}: use text of at most 2,000 characters."
                )
            value = value.strip()
        if self.type == "select":
            if value not in self.choices and not self.allow_other:
                raise ReportError(f"{self.label}: choose one of the listed options.")
        elif self.type == "date":
            try:
                parsed = date.fromisoformat(value)
                if parsed.isoformat() != value:
                    raise ValueError
            except ValueError as exc:
                raise ReportError(
                    f"{self.label}: use YYYY-MM-DD.", code="invalid_date"
                ) from exc
        elif self.type == "month":
            for pattern in ("%Y-%m", "%B %Y", "%b %Y"):
                try:
                    return datetime.strptime(value, pattern).strftime("%Y-%m")
                except ValueError:
                    pass
            raise ReportError(
                f"{self.label}: use YYYY-MM or a month and year, "
                "such as November 2026.",
                code="invalid_month",
            )
        elif self.type == "boolean":
            if value in ("yes", "no"):
                value = value == "yes"
            if type(value) is not bool:
                raise ReportError(f"{self.label}: choose Yes or No.")
        elif self.type in {"number", "integer"}:
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ReportError(f"{self.label}: enter a finite number.")
            if self.type == "integer":
                if value != int(value):
                    raise ReportError(f"{self.label}: enter a whole number.")
                value = int(value)
        return value


class InputForm(StrictModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    fields: list[InputField] = Field(min_length=1, max_length=12)
    report_reference: str | None = None

    @model_validator(mode="after")
    def unique_ids(self):
        if len({field.id for field in self.fields}) != len(self.fields):
            raise ReportError("Form field IDs must be unique.", code="invalid_form")
        return self

    def validate_answers(self, answers):
        if not isinstance(answers, dict) or answers.keys() - {
            f.id for f in self.fields
        }:
            raise ReportError(
                "Use only this form's input fields.", code="invalid_inputs"
            )
        values = {}
        for field in self.fields:
            value = field.normalize(answers.get(field.id, field.default))
            if value is not None:
                values[field.id] = value
        if len(json.dumps(values)) > 10000:
            raise ReportError("Shorten your answers to fit within 10,000 characters.")
        return values


def parameter_form(definition, reference, supplied, *, title, description):
    if supplied.keys() - definition.parameters.keys():
        raise ReportError("Use only parameters declared in the saved report.")
    fields = []
    for name, parameter in definition.parameters.items():
        value = supplied.get(name, parameter.default)
        if value is not None:
            parameter.validate_value(value)
        choices = [str(choice) for choice in parameter.choices]
        fields.append(
            InputField(
                id=name,
                label=name.replace("_", " ").capitalize(),
                type="select"
                if choices
                else "text"
                if parameter.type == "string"
                else parameter.type,
                required=parameter.required,
                choices=choices,
                default=str(value) if choices and value is not None else value,
                help=parameter.description,
            )
        )
    return InputForm(
        title=title, description=description, fields=fields, report_reference=reference
    )


def report_parameter_values(definition, answers):
    # Select controls use display strings; recover each declared choice's type.
    values = dict(answers)
    for name, parameter in definition.parameters.items():
        if name in values and parameter.choices:
            values[name] = next(
                choice for choice in parameter.choices if str(choice) == values[name]
            )
    return resolve_parameters(definition.parameters, values, definition.parameter_order)
