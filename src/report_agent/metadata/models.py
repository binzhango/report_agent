"""Serialization-independent template metadata schema."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from report_agent.metadata.dimensions import validate_dimension
from report_agent.metadata.styles import PlaceholderStyle


class MetadataModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CompilerOptions(MetadataModel):
    engine: Literal["pdflatex", "xelatex", "lualatex"] = "xelatex"


class InputDefinition(MetadataModel):
    """Reusable input constraints shared by all metadata formats."""

    type: Literal["text", "image", "graph", "table"]
    required: bool = True
    default: str | None = None
    max_chars: int | None = Field(default=None, gt=0)
    width: str | None = None
    preset: str | None = None
    precision: int | None = Field(default=None, ge=0, le=8)
    show_index: bool | None = None
    longtable: bool | None = None
    style: PlaceholderStyle | None = None
    backend: Literal["styler", "great_tables"] | None = None
    source: Literal["user", "agent"] = "user"
    prompt: str | None = None
    uses: tuple[str, ...] = ()

    @model_validator(mode="after")
    def compatible_options(self) -> "InputDefinition":
        if self.backend is not None and self.type != "table":
            raise ValueError("backend is supported only for tables.")
        if self.backend == "great_tables" and self.preset is not None:
            raise ValueError("Presets for great_tables are not implemented.")
        if self.source == "agent":
            if self.type != "text" or not self.prompt or not self.prompt.strip():
                raise ValueError(
                    "Agent sources require a text input and a non-empty prompt."
                )
        elif self.prompt is not None or self.uses:
            raise ValueError("prompt and uses require source: agent.")
        if len(set(self.uses)) != len(self.uses):
            raise ValueError("uses must contain unique table input names.")
        if self.type != "text" and (
            self.default is not None or self.max_chars is not None
        ):
            raise ValueError(
                "default and max_chars are supported only for text inputs."
            )
        if self.width is not None and self.type not in {"image", "graph"}:
            raise ValueError("width is supported only for images and graphs.")
        if self.preset is not None and self.type != "table":
            raise ValueError("preset is supported only for tables.")
        if self.type != "table" and any(
            option is not None
            for option in (self.precision, self.show_index, self.longtable)
        ):
            raise ValueError("precision, show_index, and longtable are table options.")
        if self.preset is not None and self.preset not in {
            "financial",
            "comparison",
            "heatmap_sequential",
            "heatmap_diverging",
        }:
            raise ValueError("Unsupported table preset.")
        if self.width is not None:
            validate_dimension(self.width)
        if self.longtable and self.style not in (None, PlaceholderStyle()):
            if self.style.container is not None:
                raise ValueError(
                    "Multi-page tables cannot be placed in an unbreakable box."
                )
            if self.style.layout.display != "block":
                raise ValueError("Styles on multi-page tables require display: block.")
        if (
            self.default is not None
            and self.max_chars is not None
            and len(self.default) > self.max_chars
        ):
            raise ValueError("Default text exceeds max_chars.")
        return self


class TemplateMetadata(MetadataModel):
    schema_version: Literal[1] = 1
    id: str
    entrypoint: str = "main.tex"
    compiler: CompilerOptions = Field(default_factory=CompilerOptions)
    inputs: dict[str, InputDefinition]
    provided_packages: frozenset[str] = frozenset()

    @model_validator(mode="after")
    def validate_dependencies(self) -> "TemplateMetadata":
        for name, definition in self.inputs.items():
            for dependency in definition.uses:
                if (
                    dependency not in self.inputs
                    or self.inputs[dependency].type != "table"
                ):
                    raise ValueError(
                        f"{name}: uses must refer to declared table inputs "
                        f"({dependency!r})."
                    )
        return self

    @field_validator("inputs")
    @classmethod
    def valid_input_names(
        cls, value: dict[str, InputDefinition]
    ) -> dict[str, InputDefinition]:
        if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name) for name in value):
            raise ValueError(
                "Input names must be simple identifiers starting with a letter."
            )
        return value
