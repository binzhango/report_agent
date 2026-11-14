"""Compact, escaped data-review summaries with exact details on demand."""

import json
from datetime import date
from html import escape


def label(value):
    return str(value).replace("_", " ").capitalize()


def display_value(value):
    if type(value) is bool:
        return "Yes" if value else "No"
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() == value:
                return f"{parsed.day} {parsed:%b %Y}"
        except ValueError:
            pass
    return str(value)


def data_review_html(review):
    queries = review.get("queries", {})
    params = review.get("parameters", {})
    sections = []
    operators = {"eq": "is", "ge": "≥", "gt": ">", "le": "≤", "lt": "<"}
    for name, query in queries.items():
        connection = query["connection"]
        source = review.get("source_labels", {}).get(connection) or (
            "Uploaded workbook"
            if connection.startswith("upload_")
            else label(connection)
        )
        kind = review.get("source_types", {}).get(connection)
        file_query = kind == "FileSource" or query["query"] == "data"
        http_query = kind == "HttpSource"
        facts = []
        if file_query:
            facts.append(
                (
                    "Worksheet",
                    "First worksheet" if query["query"] == "data" else query["query"],
                )
            )
        if http_query:
            facts.append(("Endpoint", query["query"]))
        facts.append(
            ("Columns", ", ".join(query.get("columns", [])) or "All available columns")
        )
        filters = []
        effective_filters = query.get("filters") or review.get(
            "source_filters", {}
        ).get(connection, {})
        for param, rule in effective_filters.items():
            if param not in query.get("parameter_bindings", {}):
                continue
            value = params.get(
                query.get("parameter_bindings", {}).get(param, param), "Not set"
            )
            filters.append(
                f"{label(rule['column'])} "
                f"{operators.get(rule.get('op', 'eq'), 'is')} {display_value(value)}"
            )
        facts.append(
            (
                "Selection",
                "; ".join(filters)
                or (
                    "All rows"
                    if file_query
                    else "Configured API request"
                    if http_query
                    else "Defined by the query below"
                ),
            )
        )
        facts.append(("Row limit", f"{query.get('row_limit', 1000):,}"))
        rows = "".join(
            f"<div><dt>{escape(k)}</dt><dd>{escape(v)}</dd></div>" for k, v in facts
        )
        bindings = query.get("parameter_bindings", {})
        if bindings and not file_query:
            rows += (
                "<div><dt>Input bindings</dt><dd>"
                + escape(
                    ", ".join(f"{key} → {value}" for key, value in bindings.items())
                )
                + "</dd></div>"
            )
        sql = (
            ""
            if file_query or http_query
            else '<div class="review-query-label">Saved query</div>'
            '<pre class="review-sql"><code>' + escape(query["query"]) + "</code></pre>"
        )
        sections.append(
            '<section class="review-query"><div class="review-source-row"><strong>'
            + escape(label(name))
            + "</strong><span>"
            + escape(source)
            + '</span></div><dl class="review-facts">'
            + rows
            + "</dl>"
            + sql
            + "</section>"
        )
    if params:
        sections.append(
            '<section class="review-inputs"><h4>Preview inputs</h4>'
            '<dl class="review-facts">'
            + "".join(
                f"<div><dt>{escape(label(k))}</dt><dd>{escape(display_value(v))}</dd></div>"
                for k, v in params.items()
            )
            + "</dl></section>"
        )
    else:
        sections.append(
            '<p class="review-empty">No runtime inputs for this preview.</p>'
        )
    exact = escape(json.dumps(review, indent=2, ensure_ascii=False))
    return (
        '<details class="data-review"><summary><span>Review data and queries</span>'
        f'<span class="review-count">{len(queries)} data section'
        + ("s" if len(queries) != 1 else "")
        + '</span></summary><div class="data-review-body">'
        + "".join(sections)
        + '<details class="review-technical"><summary>Technical details</summary><pre>'
        + exact
        + "</pre></details></div></details>"
    )
