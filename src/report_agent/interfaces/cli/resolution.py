"""Explicit CLI wiring for application-owned query and generator adapters."""

from importlib import import_module
from pathlib import Path

from report_agent.metadata.parsers import JsonMetadataParser, YamlMetadataParser
from report_agent.resolution.models import QuerySource
from report_agent.resolution.resolver import ContentResolver


def load_resolver(factory_name: str) -> ContentResolver:
    """Import trusted application code only when selected with --resolver."""
    module_name, separator, attribute = factory_name.partition(":")
    if not separator or not module_name or not attribute.isidentifier():
        raise ValueError("--resolver must name an importable module:factory.")
    try:
        factory = getattr(import_module(module_name), attribute)
        resolver = factory()
    except Exception as exc:
        raise ValueError(f"Cannot initialize resolver {factory_name!r}: {exc}") from exc
    if not isinstance(resolver, ContentResolver):
        raise ValueError("Resolver factory must return ContentResolver.")
    return resolver


def load_queries(path: Path) -> dict[str, QuerySource]:
    parsers = {
        ".json": JsonMetadataParser(),
        ".yaml": YamlMetadataParser(),
        ".yml": YamlMetadataParser(),
    }
    parser = parsers.get(path.suffix.lower())
    if parser is None:
        raise ValueError("Query bindings must be a JSON or YAML file.")
    data = parser.parse(path.read_text(encoding="utf-8"))
    if set(data) != {"queries"} or not isinstance(data["queries"], dict):
        raise ValueError("Query file must contain a 'queries' mapping only.")
    return {
        name: QuerySource.model_validate(value)
        for name, value in data["queries"].items()
    }
