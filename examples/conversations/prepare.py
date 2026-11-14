"""Create isolated, synthetic database fixtures and the sample document."""

import sqlite3
from pathlib import Path


def database(directory):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory.resolve() / "demo.sqlite"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS sales (order_date TEXT, region TEXT, "
            "product TEXT, revenue REAL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS tickets (created_date TEXT, team "
            "TEXT, title TEXT, owner TEXT, priority TEXT, status TEXT)"
        )
        if not db.execute("SELECT COUNT(*) FROM sales").fetchone()[0]:
            db.executemany(
                "INSERT INTO sales VALUES (?, ?, ?, ?)",
                [
                    ("2026-10-06", "Europe", "Core", 12450),
                    ("2026-10-15", "Europe", "Plus", 8380),
                    ("2026-10-23", "Asia", "Core", 15670),
                    ("2026-11-04", "Europe", "Core", 14890),
                    ("2026-11-18", "Europe", "Plus", 9730),
                    ("2026-11-25", "Asia", "Core", 18120),
                ],
            )
        if not db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]:
            db.executemany(
                "INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        "2026-11-02",
                        "Billing",
                        "Duplicate invoice",
                        "Maya",
                        "High",
                        "Open",
                    ),
                    (
                        "2026-11-03",
                        "Billing",
                        "Payment retry",
                        "Omar",
                        "Medium",
                        "In progress",
                    ),
                    (
                        "2026-11-06",
                        "Billing",
                        "Receipt missing",
                        "Elena",
                        "Low",
                        "Open",
                    ),
                    ("2026-11-07", "Billing", "Old refund", "Maya", "High", "Resolved"),
                    (
                        "2026-11-09",
                        "Billing",
                        "Tax correction",
                        "Elena",
                        "High",
                        "Open",
                    ),
                    ("2026-11-10", "Billing", "Card declined", "Omar", "High", "Open"),
                    (
                        "2026-11-12",
                        "Billing",
                        "Export receipt",
                        "Maya",
                        "Low",
                        "In progress",
                    ),
                    (
                        "2026-11-13",
                        "Billing",
                        "Closed dispute",
                        "Omar",
                        "Medium",
                        "Closed",
                    ),
                    ("2026-11-10", "Platform", "Login issue", "Noah", "High", "Open"),
                ],
            )
    return path


def sample_document(directory):
    import shutil

    from report_agent.application.report_runs import ReportRuns
    from report_agent.definitions.models import ReportDefinition
    from report_agent.storage.report_definitions import ReportStore

    store = ReportStore(directory / "sample_library")
    definition = ReportDefinition.model_validate(
        {
            "id": "sales_example",
            "name": "Sales reference sample",
            "layout": {
                "title": "Monthly Sales Review",
                "format": "docx",
                "blocks": [
                    {
                        "name": "intro",
                        "heading": "Introduction",
                        "text": (
                            "This review presents product revenue for"
                            " the selected region and"
                            " compares regional performance for the reporting period."
                        ),
                    },
                    {
                        "name": "products",
                        "heading": "Revenue by product",
                        "kind": "table",
                    },
                    {
                        "name": "regions",
                        "heading": "Regional comparison",
                        "kind": "chart",
                    },
                    {
                        "name": "old_commentary",
                        "heading": "Previous commentary",
                        "text": (
                            "Last year's results reflected an earlier"
                            " product mix. Replace "
                            "this historical commentary during onboarding."
                        ),
                    },
                ],
            },
            "queries": {
                "products": {
                    "connection": "demo",
                    "query": "products",
                    "columns": ["product", "revenue"],
                },
                "region_totals": {
                    "connection": "demo",
                    "query": "regions",
                    "columns": ["region", "revenue"],
                },
            },
            "charts": {
                "regions": {"table": "region_totals", "x": "region", "y": "revenue"}
            },
        }
    )
    ref = store.draft(definition)
    result = ReportRuns(store, {}, directory / "sample_runs").run(
        ref,
        {},
        sample_tables={
            "products": [
                {"product": "Core", "revenue": 12450},
                {"product": "Plus", "revenue": 8380},
            ],
            "region_totals": [
                {"region": "Europe", "revenue": 20830},
                {"region": "Asia", "revenue": 15670},
            ],
        },
    )
    if not result.output_path:
        raise RuntimeError(result.diagnostics)
    destination = Path(__file__).parent / "sales-example.docx"
    shutil.copyfile(result.output_path, destination)
    print(destination)


if __name__ == "__main__":
    root = Path("output/conversation_demo")
    print(database(root))
    sample_document(root)
