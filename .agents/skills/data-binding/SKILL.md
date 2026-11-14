---
name: data-binding
description: Configure data sources, parameterized queries, and table/chart bindings
  during template onboarding.
---

Call report_context for configured source names, then inspect_source for table/sheet names and column types. Ask what each table should show, relevant columns, time boundaries, grouping, and filters. For a new source ask the user to upload CSV/XLSX or have the operator configure a named connection. Do not ask for credentials in chat. preview_data checks the proposed source and returns five rows; confirm these match the user's intent. For uploaded files, use preview_data.filters to try parameter-to-column predicates; save them in queries.<name>.filters in the report definition. Keep SQL source stable and use named binds such as :start_date; never interpolate user values into SQL. For date windows prefer an inclusive start and exclusive end, explaining the period in user language. Map report parameter names to query argument names through parameter_bindings. Repeated runs must not alter saved source configuration. See [connector contract](references/connectors.md).
