# Data connectors

Pass `--connections connections.yaml` to `report serve` or `report run`. Paths in
file definitions are relative to the configuration file. Connection configuration
is maintained by the application operator; the model sees connection names and
query previews, not credentials.

```yaml
sources:
  uploaded_sales:
    type: file
    path: data/sales.csv
  sales_db:
    type: sql
    url_env: REPORT_DATABASE_URL
  metrics_api:
    type: http
    endpoints:
      monthly: https://example.internal/api/monthly
    header_env:
      Authorization: METRICS_AUTHORIZATION
    records_key: records
```

- **CSV/XLSX:** up to 20 MiB and 100,000 source rows. `query: data` reads CSV or the
  first workbook sheet; another query string selects an Excel sheet. Parameter
  filters live in report query bindings. File ingestion does not implement SQL
  aggregation; aggregate upstream or use a SQL source.
- **SQLite/PostgreSQL:** use SQLAlchemy URLs. SQLite is included with Python.
  PostgreSQL needs a compatible driver installed separately, such as
  `psycopg[binary]`, and a URL using `postgresql+psycopg://...`. The connector binds
  parameters, wraps queries with a server-side row bound, and uses database
  read-only execution. SQLite uses an execution deadline; PostgreSQL uses a
  statement timeout. SQL execution is intended for configured reporting sources.
- **HTTP JSON:** `query` names a configured endpoint. Values become GET query
  parameters. Responses must be a list of objects, or contain one under the
  configured top-level `records_key`. Requests have a 30-second timeout and a
  10-MiB response bound. Pagination and authenticated OAuth flows are not included.

Empty data, missing required columns, and exceeded row limits stop generation
with an actionable error. Failed runs have a run record and do not publish a
successful report. Live PostgreSQL and HTTP integrations require validation
against the actual configured source.
