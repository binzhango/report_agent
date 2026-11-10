"""Resolve with injected test adapters; no database or model service is invoked."""

import pandas as pd
import pytest

from report_agent.metadata.models import TemplateMetadata
from report_agent.models.inputs import TableInput, TextInput
from report_agent.resolution import ContentResolver, QuerySource


def metadata() -> TemplateMetadata:
    return TemplateMetadata.model_validate(
        {
            "id": "resolved",
            "inputs": {
                "sales": {"type": "table"},
                "summary": {
                    "type": "text",
                    "source": "agent",
                    "prompt": "Summarize sales",
                    "uses": ["sales"],
                },
            },
        }
    )


def test_tables_resolve_before_agent_with_bounded_summary_only() -> None:
    calls = []

    class Source:
        def fetch(self, query):
            calls.append("query")
            return pd.DataFrame(
                {"Revenue": [1.25, 2.75], "Private notes": ["secret", "secret"]}
            )

    class Generator:
        def generate(self, prompt, tables):
            calls.append("agent")
            summary = tables["sales"]
            assert summary.row_count == 2 and len(summary.columns) == 1
            assert summary.columns_omitted == 1
            assert "secret" not in repr(summary)
            assert summary.columns[0].metrics["max"] == 2.75
            return r"Revenue grew 12% & \input{not_a_command}"

    resolver = ContentResolver(
        sources={"pg": Source()}, text_generator=Generator(), summary_max_columns=1
    )
    result = resolver.resolve(
        metadata(),
        queries={
            "sales": QuerySource(
                connection="pg", query="SELECT revenue FROM allowed_view"
            )
        },
    )
    assert not result.diagnostics
    assert calls == ["query", "agent"]
    assert isinstance(result.inputs["sales"], TableInput)
    assert result.inputs["summary"] == TextInput(
        r"Revenue grew 12% & \input{not_a_command}"
    )


def test_data_source_row_limit_violation_is_not_silently_truncated() -> None:
    class Source:
        def fetch(self, query):
            return pd.DataFrame({"value": [1, 2]})

    result = ContentResolver(sources={"pg": Source()}).resolve(
        metadata(),
        queries={
            "sales": QuerySource(connection="pg", query="SELECT value", row_limit=1)
        },
    )
    assert result.diagnostics[0].code == "resolution_failed"
    assert "row limit" in result.diagnostics[0].message
    assert "sales" not in result.inputs


def test_agent_requires_resolved_dependencies_and_provider() -> None:
    result = ContentResolver(sources={}).resolve(metadata())
    assert "text generator" in result.diagnostics[0].message

    class Generator:
        def generate(self, prompt, tables):
            raise AssertionError("Must not be called without its table")

    result = ContentResolver(sources={}, text_generator=Generator()).resolve(metadata())
    assert "resolved table" in result.diagnostics[0].message


def test_explicit_agent_value_can_override_generation() -> None:
    result = ContentResolver(sources={}).resolve(
        metadata(), inputs={"summary": TextInput("Human reviewed")}
    )
    assert not result.diagnostics
    assert result.inputs["summary"].text == "Human reviewed"


@pytest.mark.parametrize(
    "definition",
    [
        {"type": "text", "prompt": "bad"},
        {"type": "table", "source": "agent", "prompt": "bad"},
        {"type": "text", "source": "agent"},
        {"type": "text", "source": "agent", "prompt": "ok", "uses": ["missing"]},
    ],
)
def test_invalid_agent_metadata_is_rejected(definition) -> None:
    with pytest.raises(ValueError):
        TemplateMetadata.model_validate(
            {"id": "invalid", "inputs": {"summary": definition}}
        )
