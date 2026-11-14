"""Queries bind values, respect row bounds, and do not mutate sources."""

import sqlite3

import pytest

from report_agent.connectors.files import FileSource
from report_agent.resolution.models import QuerySource


def test_file_date_filters_and_limits(tmp_path):
    path = tmp_path / "sales.csv"
    path.write_text("day,region,revenue\n2026-10-01,Europe,10\n2026-11-01,Europe,20\n")
    source = FileSource(
        path,
        filters={
            "start": {"column": "day", "op": "ge", "type": "date"},
            "end": {"column": "day", "op": "lt", "type": "date"},
        },
    )
    frame = source.fetch(
        QuerySource(
            connection="file",
            query="data",
            params={"start": "2026-10-01", "end": "2026-11-01"},
        )
    )
    assert frame.revenue.tolist() == [10]
    with pytest.raises(ValueError, match="filters"):
        source.fetch(QuerySource(connection="file", query="data", params={"other": 1}))
    with pytest.raises(ValueError, match="row limit"):
        source.fetch(QuerySource(connection="file", query="data", row_limit=1))


def test_sql_binds_values_and_preserves_database(tmp_path):
    pytest.importorskip("sqlalchemy")
    from report_agent.connectors.sql import SqlSource

    path = tmp_path / "source.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE sales (region TEXT, revenue INTEGER)")
        db.executemany(
            "INSERT INTO sales VALUES (?, ?)", [("Europe", 10), ("Asia", 20)]
        )
    source = SqlSource(f"sqlite:///{path}")
    query = "SELECT region, revenue FROM sales WHERE region = :region"
    assert source.fetch(
        QuerySource(connection="db", query=query, params={"region": "Europe"})
    ).revenue.tolist() == [10]
    assert source.fetch(
        QuerySource(connection="db", query=query, params={"region": "' OR 1=1 --"})
    ).empty
    with pytest.raises(ValueError, match="row limit"):
        source.fetch(
            QuerySource(connection="db", query="SELECT * FROM sales", row_limit=1)
        )
    with pytest.raises(Exception):
        source.fetch(
            QuerySource(connection="db", query="DELETE FROM sales RETURNING *")
        )
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 2


def test_http_uses_named_endpoint_and_binds_query_values(monkeypatch):
    httpx = pytest.importorskip("httpx")
    from report_agent.connectors.http import HttpSource

    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200, json={"records": [{"region": "Europe", "revenue": 12}]}
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(httpx, "stream", client.stream)
        source = HttpSource(
            {"monthly": "https://example.invalid/monthly"}, records_key="records"
        )
        frame = source.fetch(
            QuerySource(connection="api", query="monthly", params={"region": "A & B"})
        )
        assert frame.revenue.tolist() == [12]
        assert requests[0].url.params["region"] == "A & B"
        with pytest.raises(ValueError, match="configured"):
            source.fetch(QuerySource(connection="api", query="https://other.invalid"))
