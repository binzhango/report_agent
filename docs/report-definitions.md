# Reusable report definitions

`report.yaml` sits above existing `template.yaml` metadata. It defines the content
layout, fixed text, runtime parameters, query bindings, and charts. The authoring
compiler writes engine-specific source and metadata; `ReportRuns` supplies typed
inputs to the existing renderer. No runtime parameter expressions belong in style
configuration.

```yaml
schema_version: 1
id: monthly_sales
name: Monthly sales
layout:
  title: Monthly sales
  format: docx
  blocks:
    - name: introduction
      heading: Overview
      text: This report summarizes the selected reporting period.
    - name: sales
      heading: Sales by region
      kind: table
parameters:
  start_date: {type: date, description: Inclusive reporting period start}
  end_date: {type: date, description: Exclusive reporting period end}
parameter_order:
  - {before: start_date, after: end_date}
date_ranges:
  - {start: start_date, end: end_date, end_inclusive: false}
text_bindings:
  title: 'Sales: {start_date} to {end_date}'
queries:
  sales:
    connection: sales_db
    query: |
      SELECT region, SUM(revenue) AS revenue
      FROM sales
      WHERE day >= :start AND day < :end
      GROUP BY region ORDER BY region
    parameter_bindings:
      start: start_date
      end: end_date
    columns: [region, revenue]
    row_limit: 1000
```

Parameters support `string`, `integer`, `number`, `boolean`, and ISO `date` values,
plus `required`, `default`, `description`, and `choices`. Numeric values are finite
and booleans are not accepted as integers. Unknown parameters fail validation.
`parameter_order` checks matching date/numeric parameters using a strict before
relationship. Optional values referenced by a query or text binding still need
a value or default for that particular run.

`date_ranges` optionally names the start/end parameters used by calendar-month
input. Each pair must contain distinct declared date parameters, a matching
`parameter_order` rule, and no overlapping date ranges. With `end_inclusive: false`,
October 2026 becomes October 1 to November 1; with `true`, it ends October 31.
Leap years and December rollover are computed by code. The setting must match
the query/filter semantics accepted by the user.

Saved-report forms offer **Calendar month** and **Custom dates**. For older bundles
without `date_ranges`, the application recognizes ordered date pairs with simple
SQL `<`/`<=`/`BETWEEN` bounds or saved file `lt`/`le` filters. Ambiguous data-query
bounds leave custom dates available; no guess is made. Text-only legacy ranges
use an exclusive end unless the parameter description declares an inclusive end.

The agent can pass `report_month` to `request_report_inputs` or `propose_report_run`
instead of computing raw endpoints. Other supplied parameters are preserved;
conflicting supplied dates are rejected with `month_date_conflict`. Multiple
calendar ranges are selected individually in the form.

Text bindings allow only simple `{parameter}` substitutions. Attribute access,
conversion flags, and formatting expressions are rejected. Omitted text inputs
use the defaults compiled from `layout.title` and text blocks. Query values are
bound through connector APIs; SQL source is never formatted with text substitution.

A query matching a table block supplies that block. Other queries may supply chart
data without creating a visible table. A chart block has an entry in `charts`:

```yaml
charts:
  revenue_chart:
    table: sales
    x: region
    y: revenue
    kind: bar  # or line
```

Chart y values must be numeric and have at most 50 rows. Slide tables have at most
12 rows and 6 columns; slide text is capped at 700 characters per block. The engine
does not silently truncate data to satisfy limits.

For file-backed tables, save filters in the query binding so the accepted report
fully specifies its own selection rules:

```yaml
queries:
  sales:
    connection: uploaded_sales
    query: data
    parameter_bindings: {start: start_date, end: end_date}
    filters:
      start: {column: day, op: ge, type: date}
      end: {column: day, op: lt, type: date}
```

File filters support `eq`, `ge`, `gt`, `le`, and `lt`; `type: date` parses date
columns. Filters are saved per report rather than mutating a shared source. Query
`columns` specifies required returned columns, not a projection that silently
drops other columns. There is no arbitrary Python transformation execution.
