"""Bounded SQL execution. Connections must use a read-only reporting DB role."""

import time

import pandas as pd

from report_agent.errors import ReportError


class SqlSource:
    def __init__(self, url: str, *, timeout_seconds: int = 30):
        from sqlalchemy import create_engine

        self.engine = create_engine(url)
        self.timeout_seconds = timeout_seconds
        if self.engine.dialect.name not in {"sqlite", "postgresql"}:
            raise ReportError("SQL sources currently support SQLite and PostgreSQL.")

    def fetch(self, source):
        from sqlalchemy import text

        if "_report_limit" in source.params:
            raise ReportError("_report_limit is reserved.")
        query = source.query.strip().removesuffix(";")
        # Wrapping provides a server-side limit and accepts SELECT/CTE queries only.
        statement = text(
            f"SELECT * FROM (\n{query}\n) AS report_data LIMIT :_report_limit"
        )
        with self.engine.connect() as connection:
            raw = None
            try:
                if self.engine.dialect.name == "sqlite":
                    connection.exec_driver_sql("PRAGMA query_only = ON")
                    raw = connection.connection.driver_connection
                    deadline = time.monotonic() + self.timeout_seconds
                    raw.set_progress_handler(
                        lambda: int(time.monotonic() > deadline), 1000
                    )
                else:
                    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                    connection.exec_driver_sql(
                        "SET LOCAL statement_timeout = "
                        + str(int(self.timeout_seconds * 1000))
                    )
                result = connection.execute(
                    statement, {**source.params, "_report_limit": source.row_limit + 1}
                )
                rows = result.fetchmany(source.row_limit + 1)
                if len(rows) > source.row_limit:
                    raise ReportError(f"Query exceeds row limit {source.row_limit}.")
                return pd.DataFrame(rows, columns=list(result.keys()))
            finally:
                if raw is not None:
                    raw.set_progress_handler(None, 0)
                connection.rollback()
