# Resolving content before rendering

The optional `resolution` package prepares normal typed render inputs through
injected interfaces. It contains no Snowflake/Postgres driver, database credentials,
model SDK, or live SQL/LLM implementation. `ReportRenderer` does not depend on it.

```text
TemplateMetadata + supplied inputs + QuerySource bindings
                         |
                         v
                  ContentResolver
                 /               \
     DataSource.fetch()       AgentTextGenerator.generate()
           tables first        bounded summaries of uses tables
                 \               /
                         v
        ResolutionResult.inputs: TableInput / TextInput / other supplied values
                         |
                         v
             unchanged RenderRequest -> ReportRenderer -> PDF
```

## Metadata

```json
{
  "id": "sales",
  "inputs": {
    "sales": {"type": "table", "visible": false, "summary_head_rows": 5},
    "summary": {
      "type": "text",
      "source": "agent",
      "prompt": "Summarize quarterly sales",
      "uses": ["sales"],
      "max_chars": 1200
    }
  }
}
```

`source` defaults to `user`. Only agent-sourced text accepts `prompt` and `uses`.
An agent input requires a non-empty prompt and an explicit positive `max_chars`.
Every `uses` name must identify a
declared table. Agent-to-agent dependencies are not accepted; the supported
dependency order is prepared/query-backed tables followed by text.

`visible` defaults to `true`. Set `visible: false` on a context-only table that
the generator needs but the report should not display. It remains a declared,
typed, required input (unless `required: false`); the resolver fetches and
summarizes it normally. It needs no template placeholder and the renderer skips
its conversion, styling, assets, and package requirements. Referencing a hidden
input in a template is a `hidden_placeholder` error. A table in `uses` must still
be resolved even if it is optional in metadata.

The prompt may be text or an identifier understood by your generator adapter.
No prompt registry is built into the renderer. JSON/YAML metadata share the same
schema. Normal rendering still requires the resulting content to be supplied;
`source: agent` never makes the renderer invoke a model automatically.

## Python interface

Illustrative application wiring; the adapters are application-owned objects:

```python
from report_agent import RenderRequest, create_renderer
from report_agent.resolution import ContentResolver, QuerySource

resolver = ContentResolver(
    sources={"postgres_reports": my_read_only_data_source},
    text_generator=my_text_generator,
    summary_max_columns=20,
)
resolved = resolver.resolve(
    metadata,
    inputs=supplied_inputs,
    queries={
        "sales": QuerySource(
            connection="postgres_reports",
            query="SELECT region, revenue FROM reporting.quarterly_sales",
            row_limit=1000,
        )
    },
)
if resolved.diagnostics:
    handle_resolution_failure(resolved.diagnostics)
else:
    result = create_renderer().render(
        RenderRequest(template_path, metadata, resolved.inputs, output_path)
    )
```

`DataSource.fetch(QuerySource)` must return a non-empty DataFrame. The resolver
checks the returned row count and errors if the limit is exceeded; it never
silently truncates data. This check occurs **after fetching** and does not limit
query cost or execution time by itself.

The adapter must validate SQL and object access before execution, bind parameters,
use database-enforced read-only access, enforce execution/result limits, and apply
timeouts. This interface and a `row_limit` field alone do not make arbitrary SQL
safe. Live adapters require those implementations and tests before deployment.
Apply a server-side row bound **before fetching**: for example, construct a
validated query with `LIMIT row_limit + 1`, using the adapter's dialect-aware SQL
builder. Fetching the extra row lets the resolver detect an exceeded limit rather
than silently returning a truncated report. Do not append SQL blindly; adapter
validation, binding, read-only permissions, and timeouts still apply.

`AgentTextGenerator.generate(prompt, tables)` receives only a mapping of the
explicitly permitted table names to `TableSummary` objects. Each summary contains
row/column counts and up to `summary_max_columns` column profiles. Column names
are capped at 120 characters. Profiles include dtype, non-null count, and finite
numeric min/max/mean where applicable. Raw rows and free-text cells are excluded
by default. SQL, credentials, and the full DataFrame are never passed.

For category or time-series context, explicitly set `summary_head_rows` on the
table declaration (0 by default, at most 20). `TableSummary.head_rows` then holds
that many leading rows, limited to the summarized columns. Cells preserve simple
numeric/boolean values; missing/nonfinite values become `None`, and other values
are strings capped at 200 characters. Each row follows `TableSummary.columns`
order. This opt-in exposes cell values to the generator, including text, so select
only intended columns in the query. Indices are excluded.

Leading rows are a sample, not an automatic top-category or trend analysis.
For grounded rankings, query a deterministic, pre-aggregated result with explicit
ordering and opt in to enough rows. For trends, supply the intended ordered time
buckets and measures. The generator cannot infer omitted categories or periods.

Summaries remain untrusted data, not prompt instructions. The adapter owns prompt
construction, model invocation, and any factual-claim validation. Aggregate
profiles alone do not establish that generated business claims are correct.

## Resolution and error behavior

- Query results are resolved before any dependent agent text.
- Unknown bindings/connections, conflicting direct/query values, empty results,
  excess rows, missing table dependencies, and absent generators return diagnostics.
- Explicitly supplied agent text takes precedence over generation, allowing a
  reviewed value to be used without contacting a model.
- Failures can retain partial resolved inputs. Check diagnostics before rendering.
- Unexpected adapter exceptions are logged with tracebacks and become `internal_error`; cancellation exceptions
  still propagate.
- Generator output must be a string and becomes an ordinary `TextInput`. The
  resolver checks its length using the shared text policy; the renderer also
  validates supplied/overridden text and escapes it like user text. It never becomes
  trusted LaTeX.

Tests inject deterministic local doubles. They do not contact databases or models.
