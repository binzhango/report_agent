"""Load metadata through a parser registry and one shared schema."""

from collections.abc import Mapping
from pathlib import Path

from report_agent.metadata.models import TemplateMetadata
from report_agent.metadata.office import OfficeMetadata
from report_agent.metadata.parsers import (
    JsonMetadataParser,
    MetadataParser,
    YamlMetadataParser,
)

type MetadataSource = Path | Mapping[str, object] | TemplateMetadata | OfficeMetadata


class MetadataLoader:
    def __init__(self, parsers: Mapping[str, MetadataParser] | None = None) -> None:
        self._parsers = dict(
            parsers
            if parsers is not None
            else {
                ".json": JsonMetadataParser(),
                ".yaml": YamlMetadataParser(),
                ".yml": YamlMetadataParser(),
            }
        )

    def load(self, source: MetadataSource) -> TemplateMetadata | OfficeMetadata:
        if isinstance(source, (TemplateMetadata, OfficeMetadata)):
            return source
        if isinstance(source, Path):
            parser = self._parsers.get(source.suffix.lower())
            if parser is None:
                raise ValueError(f"Unsupported metadata extension: {source.suffix}")
            source = parser.parse(source.read_text(encoding="utf-8"))
        return (
            OfficeMetadata if source.get("schema_version") == 2 else TemplateMetadata
        ).model_validate(source)
