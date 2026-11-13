"""Load file-backed runtime content without coupling the renderer to file formats."""

from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, model_validator

from report_agent.metadata.parsers import JsonMetadataParser, YamlMetadataParser
from report_agent.models.inputs import (
    AnimationInput,
    ContentInput,
    GraphInput,
    ImageInput,
    TableInput,
    TextInput,
)


class InputDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["text", "image", "graph", "table", "animation"]
    text: str | None = None
    path: Path | None = None
    poster_path: Path | None = None

    @model_validator(mode="after")
    def value_matches_type(self) -> "InputDescriptor":
        if self.poster_path is not None and self.type != "animation":
            raise ValueError("poster_path is supported only for animation.")
        if self.type == "text":
            if self.text is None or self.path is not None:
                raise ValueError("Text descriptors require text and no path.")
        elif self.path is None or self.text is not None:
            raise ValueError(
                "Image, graph, and table descriptors require path and no text."
            )
        return self


class InputFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inputs: dict[str, str | InputDescriptor]


class InputFileLoader:
    def __init__(self, *, base_directory: Path | None = None) -> None:
        self._base_directory = (
            base_directory.expanduser().resolve()
            if base_directory is not None
            else None
        )
        if self._base_directory is not None and not self._base_directory.is_dir():
            raise ValueError("Input base directory must be an existing directory.")

    def load(self, path: Path) -> dict[str, ContentInput]:
        parser = (
            JsonMetadataParser()
            if path.suffix.lower() == ".json"
            else YamlMetadataParser()
            if path.suffix.lower() in {".yaml", ".yml"}
            else None
        )
        if parser is None:
            raise ValueError("Input files must be JSON or YAML.")
        file = InputFile.model_validate(parser.parse(path.read_text(encoding="utf-8")))
        result = {}
        for name, value in file.inputs.items():
            if isinstance(value, str):
                result[name] = TextInput(value)
            elif value.type == "text":
                result[name] = TextInput(value.text)
            else:
                asset = value.path.expanduser()
                if not asset.is_absolute():
                    asset = path.parent / asset
                try:
                    result[name] = self.from_path(value.type, asset)
                    if value.type == "animation" and value.poster_path is not None:
                        poster = value.poster_path.expanduser()
                        if not poster.is_absolute():
                            poster = path.parent / poster
                        checked = self.from_path("image", poster)
                        result[name] = AnimationInput(result[name].path, checked.path)
                except (OSError, ValueError) as exc:
                    raise ValueError(f"Input {name!r}: {exc}") from exc
        return result

    def from_path(self, kind: str, path: Path) -> ContentInput:
        path = path.expanduser().resolve()
        if self._base_directory is not None and not path.is_relative_to(
            self._base_directory
        ):
            raise ValueError(f"Input path is outside base directory: {path}")
        if kind == "animation":
            return AnimationInput(path, path)
        if kind == "image":
            return ImageInput(path)
        if kind == "graph":
            return GraphInput(path)
        if kind != "table":
            raise ValueError(f"Unsupported file input kind: {kind}")
        suffix = path.suffix.lower()
        if suffix == ".csv":
            frame = pd.read_csv(path)
        elif suffix == ".parquet":
            try:
                frame = pd.read_parquet(path)
            except ImportError as exc:
                raise ValueError(
                    "Parquet needs pyarrow: install report-agent[parquet] "
                    "or run uv sync --extra parquet."
                ) from exc
        else:
            raise ValueError("Table files must be CSV or Parquet.")
        return TableInput(frame)
