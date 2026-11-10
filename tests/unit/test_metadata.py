"""Verify the shared metadata contract across input formats."""

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from report_agent.metadata.loader import MetadataLoader


def test_json_yaml_and_mapping_have_equivalent_meaning(tmp_path: Path) -> None:
    data = {
        "schema_version": 1,
        "id": "sales",
        "inputs": {
            "title": {"type": "text", "max_chars": 120},
            "trend": {"type": "graph", "width": r"0.9\linewidth"},
        },
    }
    json_path = tmp_path / "template.json"
    yaml_path = tmp_path / "template.yaml"
    json_path.write_text(json.dumps(data), encoding="utf-8")
    yaml_path.write_text(yaml.safe_dump(data), encoding="utf-8")
    loader = MetadataLoader()

    assert loader.load(json_path) == loader.load(yaml_path) == loader.load(data)


@pytest.mark.parametrize("suffix, content", [(".json", "[]"), (".yaml", "- title")])
def test_metadata_requires_object_root(
    tmp_path: Path, suffix: str, content: str
) -> None:
    path = tmp_path / f"template{suffix}"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="object with string keys"):
        MetadataLoader().load(path)


def test_unsupported_schema_version_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MetadataLoader().load({"schema_version": 2, "id": "sales", "inputs": {}})


def test_parser_can_be_injected_for_another_format(tmp_path: Path) -> None:
    class CustomParser:
        def parse(self, text: str) -> dict[str, object]:
            return {"id": text.strip(), "inputs": {}}

    path = tmp_path / "template.custom"
    path.write_text("sales", encoding="utf-8")
    loader = MetadataLoader(parsers={".custom": CustomParser()})

    assert loader.load(path).id == "sales"


@pytest.mark.parametrize(
    "suffix, content",
    [
        (".json", '{"id":"a","id":"b","inputs":{}}'),
        (".yaml", "id: a\nid: b\ninputs: {}"),
        (".json", '{"id":"a","inputs":{"x":{"type":"text","type":"image"}}}'),
        (".yaml", "id: a\ninputs:\n  x:\n    type: text\n    type: image"),
    ],
)
def test_duplicate_keys_are_rejected(tmp_path: Path, suffix: str, content: str) -> None:
    path = tmp_path / f"template{suffix}"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate metadata key"):
        MetadataLoader().load(path)
