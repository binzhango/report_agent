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
| Wide tables silently overflow | Generated table spans are marked in source comments. Overfull hbox diagnostics whose source line ranges intersect those spans become `table_overflow` errors. Previous PDFs remain untouched and logs/source are retained. |
| Implicit rounding | An omitted precision preserves numeric display precision; explicit precision rounds floating values. Integer counts remain integer displays. |
| pdfLaTeX text limitations | Escape `<`, `>`, and `|` with text commands, including in OT1 templates. Keep supported pdfLaTeX examples; recommend XeLaTeX/LuaLaTeX and appropriate fonts for broader Unicode coverage. |
| Ambiguous stages | Separate metadata, template loading, output validation, input validation, content rendering, template rendering, package validation, compilation, and publication stages. |

## Package declarations

Templates still own their preamble. Requirements are checked, not injected.
The scanner follows literal `\usepackage`, `\RequirePackage`, `\documentclass`,
`\LoadClass`, and braced `\input`/`\include` dependencies inside the template bundle.
Comments and common verbatim/listing bodies are ignored.

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

## Boundaries that remain explicit

Table overflow is now an error when attributed to a generated input. This is not
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
