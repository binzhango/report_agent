"""Interchangeable file-format parsers; validation belongs to MetadataLoader."""

import json
from collections.abc import Mapping
from typing import Protocol

import yaml


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate metadata key: {key!r}")
        result[key] = value
    return result


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _yaml_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode) -> dict:
    loader.flatten_mapping(node)
    pairs = []
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str):
            raise ValueError("Metadata must use string mapping keys.")
        pairs.append((key, loader.construct_object(value_node)))
    return _unique_pairs(pairs)


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _yaml_mapping
)


class MetadataParser(Protocol):
    def parse(self, text: str) -> Mapping[str, object]: ...


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise ValueError("Metadata must be an object with string keys.")
    return value


class JsonMetadataParser:
    def parse(self, text: str) -> Mapping[str, object]:
        return _mapping(json.loads(text, object_pairs_hook=_unique_pairs))


class YamlMetadataParser:
    def parse(self, text: str) -> Mapping[str, object]:
        try:
            return _mapping(yaml.load(text, Loader=_UniqueKeyLoader))
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML metadata: {exc}") from exc
