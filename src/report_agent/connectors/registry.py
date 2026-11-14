"""Operator-configured connections; credentials are never report fields."""

import os
from pathlib import Path

import yaml

from report_agent.connectors.files import FileSource


def load_sources(path: Path | None):
    if path is None:
        return {}
    config = yaml.safe_load(path.read_text())
    if not isinstance(config, dict) or set(config) != {"sources"}:
        raise ValueError("Connections file must contain a sources mapping.")
    sources = {}
    for name, spec in config["sources"].items():
        if spec["type"] == "file":
            sources[name] = FileSource(
                path.parent / spec["path"], filters=spec.get("filters")
            )
        elif spec["type"] == "sql":
            from report_agent.connectors.sql import SqlSource

            sources[name] = SqlSource(os.environ[spec["url_env"]])
        elif spec["type"] == "http":
            from report_agent.connectors.http import HttpSource

            sources[name] = HttpSource(
                spec["endpoints"],
                headers={
                    key: os.environ[value]
                    for key, value in spec.get("header_env", {}).items()
                },
                records_key=spec.get("records_key"),
            )
        else:
            raise ValueError(f"Unknown connection type: {spec['type']}")
    return sources


def describe_source(source):
    """Expose bounded schema information without connection secrets."""
    from report_agent.connectors.http import HttpSource
    from report_agent.connectors.sql import SqlSource

    if isinstance(source, FileSource):
        import pandas as pd

        if source.path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("Data file exceeds 20 MiB.")
        sheets = ["data"]
        if source.path.suffix.lower() == ".csv":
            frame = pd.read_csv(source.path, nrows=100)
        else:
            with pd.ExcelFile(source.path, engine="openpyxl") as workbook:
                sheets = workbook.sheet_names[:30]
                frame = pd.read_excel(workbook, sheet_name=0, nrows=100)
        return {
            "type": "file",
            "sheets": sheets,
            "columns": {str(k): str(v) for k, v in frame.dtypes.items()},
        }
    if isinstance(source, SqlSource):
        from sqlalchemy import inspect

        inspector = inspect(source.engine)
        names = (inspector.get_table_names() + inspector.get_view_names())[:30]
        return {
            "type": "sql",
            "dialect": source.engine.dialect.name,
            "tables": {
                name: [
                    {"name": col["name"], "type": str(col["type"])}
                    for col in inspector.get_columns(name)[:100]
                ]
                for name in names
            },
        }
    if isinstance(source, HttpSource):
        return {
            "type": "http",
            "endpoints": list(source.endpoints),
            "records_key": source.records_key,
        }
    return {"type": type(source).__name__, "schema": "Ask the source operator."}
