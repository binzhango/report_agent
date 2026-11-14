"""Onboard once, accept, then render two months with no model calls."""

import argparse
import sqlite3
from pathlib import Path

from report_agent.application.report_runs import ReportRuns
from report_agent.connectors.sql import SqlSource
from report_agent.definitions.models import ReportDefinition
from report_agent.storage.report_definitions import ReportStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format", choices=["pdf", "docx", "pptx", "xlsx"], default="docx"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2] / "output/parameter_example"
    root.mkdir(parents=True, exist_ok=True)
    database = root / "sales.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS sales (day TEXT, region TEXT, revenue INTEGER)"
        )
        connection.execute("DELETE FROM sales")
        connection.executemany(
            "INSERT INTO sales VALUES (?, ?, ?)",
            [
                ("2026-10-15", "Europe", 120),
                ("2026-10-20", "Asia", 90),
                ("2026-11-15", "Europe", 150),
                ("2026-11-20", "Asia", 110),
            ],
        )
    definition = ReportDefinition.model_validate(
        {
            "id": "monthly_sales",
            "name": "Monthly sales",
            "description": "Saved queries with changing date parameters.",
            "layout": {
                "title": "Monthly sales",
                "format": args.format,
                "blocks": [
                    {
                        "name": "introduction",
                        "heading": "Overview",
                        "text": (
                            "Demonstration data. "
                            "This introduction is reused each month."
                        ),
                    },
                    {"name": "sales", "heading": "Revenue by region", "kind": "table"},
                ],
            },
            "parameters": {
                "start_date": {"type": "date"},
                "end_date": {"type": "date"},
            },
            "parameter_order": [{"before": "start_date", "after": "end_date"}],
            "text_bindings": {"title": "Sales: {start_date} to {end_date}"},
            "queries": {
                "sales": {
                    "connection": "sales_db",
                    "query": "SELECT region, SUM(revenue) AS revenue FROM sales "
                    "WHERE day >= :start AND day < :end "
                    "GROUP BY region ORDER BY region",
                    "parameter_bindings": {"start": "start_date", "end": "end_date"},
                    "columns": ["region", "revenue"],
                }
            },
        }
    )
    store = ReportStore(root / "library")
    runs = ReportRuns(
        store, {"sales_db": SqlSource(f"sqlite:///{database}")}, root / "runs"
    )
    draft = store.draft(definition)
    october = runs.run(draft, {"start_date": "2026-10-01", "end_date": "2026-11-01"})
    if not october.output_path:
        raise SystemExit(october.diagnostics)
    accepted = store.accept(draft, october.output_path)
    november = runs.run(
        accepted, {"start_date": "2026-11-01", "end_date": "2026-12-01"}
    )
    if not november.output_path:
        raise SystemExit(november.diagnostics)
    print(f"Accepted template: {accepted}")
    print(f"October: {october.output_path}")
    print(f"November: {november.output_path}")


if __name__ == "__main__":
    main()
