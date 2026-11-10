"""One source of truth for plain-text input policy."""

from report_agent.metadata.models import InputDefinition
from report_agent.models.inputs import TextInput


def text_issues(
    value: object, definition: InputDefinition
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
    if any(ord(char) < 32 and char not in "\n\r\t" for char in value.text):
        return (("invalid_text", "Text contains unsupported control characters."),)
    return ()
