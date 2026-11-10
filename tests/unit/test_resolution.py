"""Resolve with injected test adapters; no database or model service is invoked."""

import json

import pandas as pd
import pytest

from report_agent.metadata.models import TemplateMetadata
from report_agent.models.inputs import TableInput, TextInput
from report_agent.resolution import ContentResolver, GenerationRequest, QuerySource


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
                    "max_chars": 1200,
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
        def generate(self, request):
            calls.append("agent")
            assert request.max_chars == 1200 and request.retry_feedback is None
            summary = request.tables["sales"]
            assert summary.row_count == 2 and len(summary.columns) == 1
            assert summary.columns_omitted == 1
            assert summary.head_rows == ()
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
        def generate(self, request):
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
        {"type": "text", "source": "agent", "prompt": "ok"},
        {
            "type": "text",
            "source": "agent",
            "prompt": "ok",
            "uses": ["missing"],
            "max_chars": 1200,
        },
    ],
)
def test_invalid_agent_metadata_is_rejected(definition) -> None:
    with pytest.raises(ValueError):
        TemplateMetadata.model_validate(
            {"id": "invalid", "inputs": {"summary": definition}}
        )


def test_opt_in_summary_rows_are_bounded_and_allow_category_context() -> None:
    spec = metadata().model_dump()
    spec["inputs"]["sales"].update(visible=False, summary_head_rows=2)
    frame = pd.DataFrame(
        {
            "Category": ["Top region", "x" * 300, "Omitted"],
            "Revenue": [20.0, float("nan"), 10.0],
            "Private": ["omitted"] * 3,
        }
    )

    class Generator:
        def generate(self, request):
            summary = request.tables["sales"]
            assert summary.head_rows == (("Top region", 20.0), ("x" * 200, None))
            assert summary.columns_omitted == 1
            assert "omitted" not in repr(summary.head_rows)
            return "Reviewed top region"

    result = ContentResolver(
        sources={}, text_generator=Generator(), summary_max_columns=2
    ).resolve(
        TemplateMetadata.model_validate(spec), inputs={"sales": TableInput(frame)}
    )
    assert not result.diagnostics


def test_generated_text_length_is_checked_and_internal_failures_are_logged(
    caplog,
) -> None:
    class TooLong:
        def generate(self, request):
            return "x" * 1201

    inputs = {"sales": TableInput(pd.DataFrame({"value": [1]}))}
    result = ContentResolver(sources={}, text_generator=TooLong()).resolve(
        metadata(), inputs=inputs
    )
    assert result.diagnostics[0].code == "resolution_failed"
    assert "summary" not in result.inputs

    class Broken:
        def generate(self, request):
            raise TypeError("broken adapter")

    result = ContentResolver(sources={}, text_generator=Broken()).resolve(
        metadata(), inputs=inputs
    )
    assert result.diagnostics[0].code == "internal_error"
    assert any(record.exc_info for record in caplog.records)


@pytest.mark.parametrize("retry_succeeds", [True, False])
def test_generator_receives_limit_and_exactly_one_length_retry(retry_succeeds) -> None:
    requests = []
    fetches = []
    spec = metadata().model_dump()
    spec["inputs"]["summary"]["max_chars"] = 50

    class Source:
        def fetch(self, query):
            fetches.append(query)
            return pd.DataFrame({"Revenue": [123]})

    class Generator:
        def generate(self, request: GenerationRequest):
            requests.append(request)
            if len(requests) == 1:
                assert request.retry_feedback is None
                return "x" * 200
            assert len(requests) == 2
            assert "200" in request.retry_feedback and "50" in request.retry_feedback
            return "Short enough." if retry_succeeds else "x" * 200

    result = ContentResolver(
        sources={"db": Source()}, text_generator=Generator()
    ).resolve(
        TemplateMetadata.model_validate(spec),
        queries={"sales": QuerySource(connection="db", query="SELECT revenue")},
    )
    assert len(fetches) == 1
    assert len(requests) == 2
    assert all(request.max_chars == 50 for request in requests)
    assert requests[0].prompt == requests[1].prompt == "Summarize sales"
    assert requests[0].tables is requests[1].tables
    if retry_succeeds:
        assert not result.diagnostics
        assert result.inputs["summary"] == TextInput("Short enough.")
    else:
        assert result.diagnostics[0].code == "resolution_failed"
        assert result.diagnostics[0].input_name == "summary"
        assert "summary" not in result.inputs


def test_non_length_validation_failure_is_not_retried() -> None:
    requests = []

    class Generator:
        def generate(self, request):
            requests.append(request)
            return "bad\x00text"

    result = ContentResolver(sources={}, text_generator=Generator()).resolve(
        metadata(), inputs={"sales": TableInput(pd.DataFrame({"value": [1]}))}
    )
    assert len(requests) == 1
    assert result.diagnostics[0].code == "resolution_failed"


@pytest.mark.parametrize("character", ["x", "é", "\\"])
def test_raw_row_budget_is_shared_across_all_context_tables(character) -> None:
    spec = metadata().model_dump()
    spec["inputs"]["sales"]["summary_head_rows"] = 20
    spec["inputs"]["raw"] = {"type": "table", "visible": False, "summary_head_rows": 20}
    spec["inputs"]["summary"]["uses"] = ["sales", "raw"]
    frame = pd.DataFrame({f"Column{i}": [character * 200] * 20 for i in range(20)})

    class Generator:
        def generate(self, request):
            summaries = request.tables
            total = sum(
                len(
                    json.dumps(
                        summary.head_rows, ensure_ascii=False, separators=(",", ":")
                    )
                )
                for summary in summaries.values()
                if summary.head_rows
            )
            assert total <= 8192
            assert 0 < len(summaries["sales"].head_rows) < 20
            assert summaries["raw"].head_rows == ()
            assert summaries["raw"].head_rows_omitted == 20
            assert summaries["sales"].head_rows_omitted == 20 - len(
                summaries["sales"].head_rows
            )
            return "Reviewed bounded data."

    result = ContentResolver(sources={}, text_generator=Generator()).resolve(
        TemplateMetadata.model_validate(spec),
        inputs={"sales": TableInput(frame), "raw": TableInput(frame)},
    )
    assert not result.diagnostics


@pytest.mark.parametrize("budget, expected_rows", [(0, 0), (12, 1), (13, 2)])
def test_raw_row_budget_boundary_preserves_complete_leading_rows(budget, expected_rows):
    spec = metadata().model_dump()
    spec["inputs"]["sales"]["summary_head_rows"] = 2

    class Generator:
        def generate(self, request):
            assert request.tables["sales"].head_rows == (("a",), ("b",))[:expected_rows]
            assert request.tables["sales"].head_rows_omitted == 2 - expected_rows
            return "Reviewed."

    result = ContentResolver(
        sources={}, text_generator=Generator(), summary_max_row_chars=budget
    ).resolve(
        metadata=TemplateMetadata.model_validate(spec),
        inputs={"sales": TableInput(pd.DataFrame({"Category": ["a", "b"]}))},
    )
    assert not result.diagnostics


def test_unreferenced_hidden_input_is_rejected_by_metadata() -> None:
    with pytest.raises(ValueError, match="Hidden inputs must be referenced.*raw"):
        TemplateMetadata.model_validate(
            {
                "id": "dead",
                "inputs": {
                    "raw": {"type": "table", "visible": False},
                    "summary": {"type": "text"},
                },
            }
        )
