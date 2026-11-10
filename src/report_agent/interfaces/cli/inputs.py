"""Load file-backed runtime content without coupling the renderer to file formats."""

from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, model_validator

from report_agent.metadata.parsers import JsonMetadataParser, YamlMetadataParser
from report_agent.models.inputs import (
    ContentInput,
    GraphInput,
    ImageInput,
    TableInput,
    TextInput,
)


class InputDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["text", "image", "graph", "table"]
    text: str | None = None
    path: Path | None = None

    @model_validator(mode="after")
    def value_matches_type(self) -> "InputDescriptor":
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
                except (OSError, ValueError) as exc:
                    raise ValueError(f"Input {name!r}: {exc}") from exc
        return result

    @staticmethod
    def from_path(kind: str, path: Path) -> ContentInput:
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
