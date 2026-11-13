"""Strict Office metadata; independent of the legacy TeX schema."""

from typing import Literal

from pydantic import Field, model_validator

from report_agent.metadata.models import MetadataModel


class ExportOptions(MetadataModel):
    format: Literal["gif", "mp4"] = "gif"
    fps: int = Field(default=12, ge=1, le=30)
    duration_seconds: float = Field(default=8, gt=0, le=30, allow_inf_nan=False)
    width_px: int = Field(default=1200, ge=2, le=1920)
    height_px: int = Field(default=600, ge=2, le=1080)
    poster_frame: Literal["first", "last"] = "last"

    @model_validator(mode="after")
    def bounded(self):
        if self.fps * self.duration_seconds > 900:
            raise ValueError("Animation exceeds 900 frames.")
        if self.format == "mp4" and (self.width_px % 2 or self.height_px % 2):
            raise ValueError("MP4 dimensions must be even.")
        return self


class OfficeInputDefinition(MetadataModel):
    type: Literal["text", "table", "image", "graph", "animation"]
    required: bool = True
    visible: bool = True
    default: str | None = None
    max_chars: int | None = Field(default=None, gt=0)
    source: Literal["user", "agent", "generator"] = "user"
    prompt: str | None = None
    uses: tuple[str, ...] = ()
    summary_head_rows: int = Field(default=0, ge=0, le=20)
    generator: str | None = None
    export: ExportOptions | None = None

    @model_validator(mode="after")
    def compatible(self):
        if self.type != "text" and any(
            v is not None for v in (self.default, self.max_chars)
        ):
            raise ValueError("default/max_chars require text.")
        if (
            self.default is not None
            and self.max_chars
            and len(self.default) > self.max_chars
        ):
            raise ValueError("Default exceeds max_chars.")
        if self.source == "agent":
            if self.type != "text" or not self.prompt or not self.max_chars:
                raise ValueError("Agent text requires prompt and max_chars.")
        elif self.prompt is not None:
            raise ValueError("prompt requires agent source.")
        if self.source == "generator":
            if self.type != "animation" or not self.generator or not self.uses:
                raise ValueError(
                    "Generator requires animation, generator name and uses."
                )
        elif self.generator is not None or self.export is not None:
            raise ValueError("generator/export require generator source.")
        if self.uses and self.source == "user":
            raise ValueError("uses requires an agent or generator.")
        if len(set(self.uses)) != len(self.uses):
            raise ValueError("Duplicate dependencies.")
        if self.summary_head_rows and self.type != "table":
            raise ValueError("summary_head_rows requires table.")
        return self


class OfficeDocument(MetadataModel):
    engine: Literal["libreoffice"]
    format: Literal["docx", "xlsx", "pptx"]


class OfficeMetadata(MetadataModel):
    schema_version: Literal[2]
    id: str
    entrypoint: str
    document: OfficeDocument
    inputs: dict[str, OfficeInputDefinition]

    @model_validator(mode="after")
    def dependencies(self):
        import re

        expected = {"docx": ".fodt", "xlsx": ".fods", "pptx": ".fodp"}[
            self.document.format
        ]
        if not self.entrypoint.endswith(expected):
            raise ValueError(f"Entrypoint must end in {expected}.")
        used = set()
        for name, definition in self.inputs.items():
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
                raise ValueError("Invalid input name.")
            if definition.type == "animation" and self.document.format != "pptx":
                raise ValueError("Animation inputs require PPTX output.")
            for dependency in definition.uses:
                if (
                    dependency not in self.inputs
                    or self.inputs[dependency].type != "table"
                ):
                    raise ValueError("uses must reference declared tables.")
                used.add(dependency)
        if any(not d.visible and n not in used for n, d in self.inputs.items()):
            raise ValueError("Hidden inputs must have a declared consumer.")
        return self
