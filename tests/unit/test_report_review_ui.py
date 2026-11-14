"""Review content stays readable while preserving exact query evidence safely."""

from report_agent.interfaces.gradio.report_review import data_review_html


def test_file_review_uses_filename_and_filters_with_technical_data_collapsed():
    review = {
        "queries": {
            "milestones": {
                "connection": "upload_private_id",
                "query": "data",
                "columns": ["project", "milestone", "owner"],
                "row_limit": 1000,
                "parameter_bindings": {"project": "project"},
                "filters": {"project": {"column": "project", "op": "eq"}},
            }
        },
        "source_labels": {"upload_private_id": "milestones.xlsx"},
        "source_types": {"upload_private_id": "FileSource"},
        "parameters": {"project": "Atlas"},
    }
    rendered = data_review_html(review)
    summary = rendered.split('<details class="review-technical">')[0]
    assert "milestones.xlsx" in summary
    assert "upload_private_id" not in summary
    assert "First worksheet" in summary
    assert "Project is Atlas" in summary
    assert "1,000" in summary
    assert "review-sql" not in summary
    assert (
        "upload_private_id" in rendered
    )  # Exact evidence remains available on demand.
    assert '<details class="review-technical" open' not in rendered


def test_query_review_escapes_markup_and_preserves_the_saved_sql():
    sql = (
        "SELECT amount FROM sales WHERE day < :end AND note = '<script>bad()</script>'"
    )
    rendered = data_review_html(
        {
            "queries": {
                "<script>name</script>": {
                    "connection": "db",
                    "query": sql,
                    "columns": [],
                    "parameter_bindings": {"end": "end_date"},
                }
            },
            "parameters": {"end_date": "2026-12-01"},
        }
    )
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "day &lt; :end" in rendered
    assert "end → end_date" in rendered
    assert "1 Dec 2026" in rendered


def test_file_review_includes_only_active_configured_source_filters():
    rendered = data_review_html(
        {
            "queries": {
                "sales": {
                    "connection": "file",
                    "query": "data",
                    "parameter_bindings": {"region": "region"},
                }
            },
            "parameters": {"region": "Europe"},
            "source_filters": {
                "file": {
                    "region": {"column": "region", "op": "eq"},
                    "unused": {"column": "day", "op": "gt"},
                }
            },
        }
    ).split('<details class="review-technical">')[0]
    assert "Region is Europe" in rendered
    assert "Not set" not in rendered and "All rows" not in rendered


def test_http_review_shows_named_endpoint_without_a_fake_sql_editor():
    rendered = data_review_html(
        {
            "queries": {
                "metrics": {
                    "connection": "metrics_api",
                    "query": "monthly",
                    "parameter_bindings": {"team": "team"},
                }
            },
            "parameters": {"team": "Atlas"},
            "source_types": {"metrics_api": "HttpSource"},
        }
    )
    assert "Endpoint" in rendered and "monthly" in rendered
    assert "review-sql" not in rendered
