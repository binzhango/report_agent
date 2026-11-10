# Renderer review changes

Implemented in response to the supplied review. The renderer remains independent
of optional data/agent preparation.

| Review item | Implementation |
| --- | --- |
| Unused package requirements | After content preparation, validate each input's package requirements against literal package declarations, local TeX/class/style dependencies, and an explicit external-package manifest. Missing requirements return `missing_package` with the input name before compilation. |
| Unexpected exceptions escape | Final `Exception` boundaries return `internal_error` with the stage and, for content failures, the input name. `KeyboardInterrupt`/`SystemExit` still propagate. |
| Backend collisions | Registry keys are `(type, backend)`; tables default to Styler. `backend: great_tables` is recognized, but no Great Tables adapter is registered. Selection fails clearly before compilation. Its presets are not implemented or advertised as supported. |
| Duplicated text rules | One `text_issues` policy is shared by aggregate preflight and standalone TextRenderer calls. Adapters retain defensive checks without independently defining length/type rules. |
| Text-only CLI | Added JSON/YAML `--inputs`, CSV/Parquet `--table`, `--image`, and `--graph`. Input-manifest paths are relative to the manifest; explicit flag paths are relative to the working directory. Explicit flags override manifest values; duplicate explicit names are rejected. |
| Wide tables silently overflow | Generated table spans are marked in source comments. Attributed overfull hboxes produce `table_overflow`: warning up to `compiler.table_overflow_tolerance_pt` (default 2pt), error above it. Failed builds preserve previous PDFs and retain logs/source. |
| Colored-cell dependencies | Heatmaps/comparison tables require `colortbl` as well as `xcolor`. The scanner treats `\usepackage[table]{xcolor}` as supplying both; plain `xcolor` supplies only itself. |
| Agent-only context | `visible: false` inputs are resolved and validated but need no placeholder and are never rendered. Agent inputs require explicit `max_chars`; optional `summary_head_rows` adds bounded category/time-series context. |
| Generation constraints | `GenerationRequest` supplies `max_chars` to the generator; a length violation permits one retry with feedback before hard failure. |
| Raw context size | Opt-in raw rows share an 8,192-character JSON budget across all tables in a generation request. Trailing rows are dropped and omission counts are exposed. |
| Dead hidden declarations | Metadata rejects hidden inputs that no agent `uses` references. |
| Implicit rounding | An omitted precision preserves numeric display precision; explicit precision rounds floating values. Integer counts remain integer displays. |
| pdfLaTeX text limitations | Escape `<`, `>`, and `|` with text commands, including in OT1 templates. Keep supported pdfLaTeX examples; recommend XeLaTeX/LuaLaTeX and appropriate fonts for broader Unicode coverage. |
| Ambiguous stages | Separate metadata, template loading, output validation, input validation, content rendering, template rendering, package validation, compilation, and publication stages. |

## Package declarations

Templates still own their preamble. Requirements are checked, not injected.
The scanner follows literal `\usepackage`, `\RequirePackage`, `\documentclass`,
`\LoadClass`, and braced `\input`/`\include` dependencies inside the template bundle.
Comments and common verbatim/listing bodies are ignored.
Options are inspected: `xcolor` with the `table` option supplies `colortbl` for
generated cell colors. Loading `colortbl` explicitly also satisfies that requirement.
The scanner follows literal commands and local dependencies in source order.
Forward `table` via `\PassOptionsToPackage{table}{xcolor}` or the global
`\documentclass[table]{...}` option before the first `xcolor` load.
These options alone do not imply that `xcolor` itself was loaded. External
class/style dependencies still use `provided_packages` when they cannot be scanned.

For a package supplied indirectly by an external class/style or macro-generated
loading logic, the trusted template author can declare:

```json
{"provided_packages": ["graphicx", "booktabs"]}
```

This is an assertion that the template loads those packages, not a request to load
them. The scanner is not a full TeX interpreter: it cannot prove arbitrary macro
or conditional execution, or that an installed compiler contains every package.
Keep ordinary dependencies explicit; compilation remains the final authority.

## Input manifest

```yaml
inputs:
  summary: Quarterly sales review
  logo: {type: image, path: assets/logo.png}
  trend: {type: graph, path: assets/trend.pdf}
  sales: {type: table, path: data/sales.csv}
```

JSON is equivalent. A text descriptor `{type: text, text: ...}` is also supported.
Figure objects remain Python-only; file-based graphs cover the CLI equivalent.

```sh
uv run report render path/to/template \
  --metadata path/to/template/template.json \
  --inputs path/to/inputs.yaml \
  --text 'summary=Reviewed override' \
  --output output/pdf/review.pdf
```

Parquet support is optional: `uv sync --extra parquet`, or install
`report-agent[parquet]`. CSV does not require that extra.

The local CLI permits arbitrary asset paths by default. For agent/API-created
manifests, use `InputFileLoader(base_directory=allowed_directory)` or CLI
`--input-root path/to/allowed-directory`. It checks resolved file paths before
reading CSV/Parquet or accepting image/graph paths, rejecting absolute paths,
parent traversal, and symlinks that resolve outside the root. Explicit CLI asset
flags follow the same restriction. Relative manifest paths still resolve against
the manifest location. The restriction covers referenced assets, not the manifest,
template, metadata, or output paths. It assumes the allowed filesystem is not
being changed concurrently; it is not process isolation.

## Overflow tolerance

```json
{"compiler": {"engine": "xelatex", "table_overflow_tolerance_pt": 2.0}}
```

Tolerance must be finite and non-negative. Attributed width at or below it is a
warning and permits publication. Greater width is an error; zero makes any
positive reported overflow fail. Unknown-width attributed overflow fails
conservatively. The setting classifies reported diagnostics; it does not change
TeX's own warning thresholds or physically resize a table.

## Boundaries that remain explicit

Table overflow above tolerance is an error when attributed to a generated input. This is not
automatic column splitting, resizing, or landscape selection. Unattributed/static
template overflow remains a compiler warning. Line-range attribution is based on
the expanded entrypoint; arbitrary nested TeX file execution is not a complete
source-mapping system.

Templates remain trusted. Sandboxed Jinja, escaping, and disabled shell escape do
not make arbitrary uploaded TeX safe. No public template-upload API was added.
`openin_any`/`openout_any` are not claimed as isolation controls for texres without
engine-specific verification; untrusted templates require a tested filesystem/
process isolation boundary.

[Content resolution](content-resolution.md) now provides injectable data-source
and text-generator interfaces, dependency ordering, bounded table summaries, and
structured results. Live SQL/LLM adapters are deliberately absent.
