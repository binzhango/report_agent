"""File-backed CLI content is parsed independently of rendering."""

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from report_agent.interfaces.cli.inputs import InputFileLoader
from report_agent.models.inputs import GraphInput, ImageInput, TableInput, TextInput


@pytest.mark.parametrize("suffix", ["json", "yaml"])
def test_input_files_load_relative_assets_and_csv(tmp_path: Path, suffix: str) -> None:
    (tmp_path / "data.csv").write_text("region,revenue\nEMEA,1320\n")
    manifest = {
        "inputs": {
            "summary": "Review",
            "logo": {"type": "image", "path": "logo.png"},
            "trend": {"type": "graph", "path": "trend.pdf"},
            "sales": {"type": "table", "path": "data.csv"},
        }
    }
    path = tmp_path / f"inputs.{suffix}"
    path.write_text(
        json.dumps(manifest) if suffix == "json" else yaml.safe_dump(manifest)
    )
    result = InputFileLoader().load(path)
    assert result["summary"] == TextInput("Review")
    assert result["logo"] == ImageInput(tmp_path / "logo.png")
    assert result["trend"] == GraphInput(tmp_path / "trend.pdf")
    assert isinstance(result["sales"], TableInput)
    assert result["sales"].data.iloc[0]["region"] == "EMEA"


def test_parquet_table_loader(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    frame = pd.DataFrame({"value": [1.25]})
    path = tmp_path / "data.parquet"
    frame.to_parquet(path)
    result = InputFileLoader().from_path("table", path)
    pd.testing.assert_frame_equal(frame, result.data)


def test_input_descriptors_reject_ambiguous_values(tmp_path: Path) -> None:
    path = tmp_path / "inputs.json"
    path.write_text(
        json.dumps({"inputs": {"summary": {"type": "text", "text": "a", "path": "b"}}})
    )
    with pytest.raises(ValueError, match="no path"):
        InputFileLoader().load(path)


@pytest.mark.parametrize("kind", ["table", "image", "graph"])
@pytest.mark.parametrize("style", ["absolute", "traversal", "symlink"])
def test_restricted_loader_rejects_assets_outside_root_before_reading(
    tmp_path: Path, kind: str, style: str
) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    outside = tmp_path / "private.csv"
    outside.write_text("private\nsecret\n")
    path = outside if style == "absolute" else root / "../private.csv"
    if style == "symlink":
        path = root / "link.csv"
        path.symlink_to(outside)
    manifest = root / "inputs.json"
    manifest.write_text(
        json.dumps({"inputs": {"asset": {"type": kind, "path": str(path)}}})
    )
    loader = InputFileLoader(base_directory=root)
    with pytest.raises(ValueError, match="outside base directory"):
        loader.load(manifest)
    with pytest.raises(ValueError, match="outside base directory"):
        loader.from_path(kind, path)


def test_restricted_loader_accepts_inside_assets(tmp_path: Path) -> None:
    (tmp_path / "data.csv").write_text("value\n1\n")
    manifest = tmp_path / "inputs.json"
    manifest.write_text(
        json.dumps({"inputs": {"data": {"type": "table", "path": "data.csv"}}})
    )
    result = InputFileLoader(base_directory=tmp_path).load(manifest)
    assert result["data"].data.iloc[0, 0] == 1
