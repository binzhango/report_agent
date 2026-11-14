"""One source of truth for plain-text input policy."""

import re

from report_agent.metadata.models import InputDefinition
from report_agent.metadata.office import OfficeInputDefinition
from report_agent.models.inputs import TextInput

_INVALID_XML_CHAR = re.compile(
    "[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]"
)


def invalid_xml_text(text: str) -> bool:
    """Reject characters outside the XML 1.0 Char production, including surrogates."""
    return _INVALID_XML_CHAR.search(text) is not None


def text_issues(
    value: object, definition: InputDefinition | OfficeInputDefinition
) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, TextInput) or not isinstance(value.text, str):
        return (("input_type", "Expected TextInput with a string value."),)
    if definition.max_chars is not None and len(value.text) > definition.max_chars:
        return (
            (
                "text_length",
                f"Text exceeds the {definition.max_chars}-character limit.",
            ),
        )
    if invalid_xml_text(value.text):
        return (("invalid_text", "Text contains characters forbidden by XML 1.0."),)
    return ()
