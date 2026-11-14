# Validation, diagnostics and publication

This reference covers the current shared render contracts and PDF-specific
package/overflow checks. The [architecture](project-overview.md) describes backend
dispatch; [Office contracts](office-reports.md) describe Flat ODF, conversion and
animation restrictions.

## Validation and resolution order

`ReportRenderer` first parses schema-v1 or schema-v2 metadata. If query bindings or
non-user sources are present, it runs the configured `ContentResolver` before
calling the selected backend. Supplied values override agent/generator inputs.
An absent required adapter produces `resolution_failed`, not a backend
`missing_input` error. See [resolution wiring](content-resolution.md).

The PDF and Office backends then check output paths, template/input compatibility
and typed values. Visible declarations need a matching placeholder; hidden context
tables must have a declared agent/generator consumer and cannot have a visible
placeholder. Missing required values fail unless an applicable default exists.
Omitted optional values are allowed, but declarations still need compatible types
and slots/backends.

`text_issues` is shared by PDF validation, Office validation, agent text checking
and the standalone PDF `TextRenderer`. It checks `TextInput`, string type,
character limit and the XML 1.0 character set. Unsupported control characters,
lone surrogates, U+FFFE and U+FFFF fail before compilation/conversion, with an input
name on backend input-validation diagnostics. This does not guarantee a selected
font has a glyph for every otherwise valid character.

For PDF, registry keys are `(type, backend)` and tables default to Styler.
`backend: great_tables` is recognized by schema v1 but has no bundled renderer;
selecting it returns `unsupported_backend`, including on omitted optional inputs.
Office tables use `OdfTemplate` and do not use that registry or its presets.

## Package declarations

These rules apply to LaTeX/PDF only. Templates own their preamble; requirements
are checked rather than injected. The scanner follows literal `\usepackage`,
`\RequirePackage`, `\documentclass`, `\LoadClass` and braced `\input`/`\include`
dependencies within the template bundle. Comments and common verbatim/listing
bodies are ignored.

Colored table cells need `colortbl` as well as `xcolor`.
`\usepackage[table]{xcolor}` supplies both; plain `xcolor` supplies only itself.
The scanner follows declarations in source order. Forward the `table` option with
`\PassOptionsToPackage{table}{xcolor}` or the global `\documentclass[table]{...}`
option before the first `xcolor` load. An option alone does not load the package.

For a package supplied by an external class or macro-generated loading logic,
the trusted template author can assert:

```json
{"provided_packages": ["graphicx", "booktabs"]}
```

This states that the template supplies those packages. It does not request their
insertion or installation. The scanner is not a TeX interpreter and cannot prove
arbitrary macro execution. Missing declared requirements return `missing_package`
with the input name before compilation; the compiler checks actual availability.

## Input manifest

Both backends accept the same runtime-file manifest structure:

```yaml
inputs:
  summary: Quarterly sales review
  logo: {type: image, path: assets/logo.png}
  trend: {type: graph, path: assets/trend.png}
  sales: {type: table, path: data/sales.csv}
```

JSON is equivalent. Text also accepts `{type: text, text: ...}`. PDF graphics can
use PNG/JPEG/PDF; Office image/graph slots accept PNG/JPEG. Live `FigureInput`
objects enter through Python. PPTX animation descriptors use
`{type: animation, path: assets/chart.gif, poster_path: assets/poster.png}`;
`poster_path` is optional and defaults to the animation file for poster staging.

```sh
uv run report render path/to/template \
  --metadata path/to/template/template.yaml \
  --inputs path/to/inputs.yaml \
  --text 'summary=Reviewed override' \
  --output output/review.docx
```

Choose an output suffix matching the template metadata. Explicit flags override
manifest values, and repeated explicit input names are rejected. Manifest asset
paths are relative to the manifest; explicit flag paths are relative to the
working directory. CSV is included; Parquet requires `uv sync --locked --extra
parquet` or `report-agent[parquet]`.

`--resolver module:factory` and `--queries queries.yaml` configure the normal
resolution path. The factory is explicit trusted application code selected by the
caller, not imported from template metadata. Query bindings use a separate file;
a name cannot have both a query and a supplied value.

The CLI permits arbitrary asset paths by default. `--input-root DIRECTORY` or
`InputFileLoader(base_directory=...)` checks resolved asset paths before reading
CSV/Parquet or accepting media references, including animation posters. Paths
outside the allowed root are rejected, whether absolute, traversing or symlinked.
Paths inside it can be absolute. This restriction covers assets, not the manifest,
template, metadata or output. It assumes the filesystem stays stable during the
build and is not process isolation.

## Overflow tolerance

This setting applies to schema-v1 PDF tables:

```json
{"compiler": {"engine": "xelatex", "table_overflow_tolerance_pt": 2.0}}
```

Generated table spans carry source markers. Attributed overfull hboxes at or
below the finite, nonnegative tolerance warn; greater width fails publication.
Zero makes any positive attributed overflow fail. Unknown-width attributed
overflow fails conservatively. Unattributed/static template overflow remains a
compiler warning. Nested TeX execution is not a complete source-mapping system.

The setting classifies reported diagnostics. It does not resize tables, choose
landscape, split columns or change TeX warning thresholds. Office has no equivalent
TeX overflow tolerance: inspect native document/slide layout after conversion.

## Publication and failure behavior

Final report paths and artifact destinations are checked against source resources.
Each output stem owns a sibling `.artifacts` directory. `publish_snapshot` stages
a complete replacement before switching directories, so old hashes and failure
logs do not accumulate. If staging fails, the previous snapshot remains. Callers
must serialize writes to the same destination and use distinct output stems for
concurrent reports, including reports with different output formats.

A successful build publishes the final report after artifacts. Those two
publications are not a single transaction. Conversion/compiler failures preserve
the old final report and retain available diagnostic artifacts; early validation
failures may have no new artifacts. An Office failure to retain diagnostic files
adds `artifact_retention_failed` without masking the original conversion error.

`RenderResult.output_path` is the cross-format success field. `pdf_path` is only
a PDF alias. The CLI prints diagnostics to stderr and a successful path to stdout;
render failures exit 1, while invalid CLI arguments exit 2. Warnings alone do not
mean failure, including the current Office `experimental_backend` warning.

| Stage / diagnostic | What to inspect |
| --- | --- |
| `metadata / invalid_input` | Schema, format, fields, parsing and duplicate keys |
| `resolution / resolution_failed` | Adapters, queries, dependency tables and generated content |
| `input_validation / missing_input`, `input_type`, `invalid_text`, `text_length` | Named runtime values/defaults and text policy |
| `input_validation / undeclared_placeholder`, `unused_input`, `hidden_placeholder`, `invalid_slot` | Template/metadata names, visibility and slot type |
| `package_validation / missing_package` | PDF preamble or `provided_packages` |
| `compilation / table_overflow` | PDF table width and tolerance |
| `compilation / compiler_*` | texres executable, compiler log and process lifetime |
| `conversion / converter_*`, `missing_output` | LibreOffice executable, version and retained conversion log |
| `output_validation / invalid_office_package`, `animation_not_preserved` | Office ZIP structure, relationships and original animated media |
| `publication / artifact_retention_failed` | Filesystem/storage error retaining an Office failure's artifacts |

Format-specific failures can also report `invalid_input`, `build_failed` or
`internal_error`. Diagnostics carry input names where the failure can be attributed.
Cancellation exceptions such as `KeyboardInterrupt` propagate; owned workspaces
and process cleanup still apply.

## Trusted-source boundary

Templates and registered Python generators are trusted. TeX escaping, sandboxed
Jinja and disabled shell escape do not make arbitrary TeX safe. Office rejects
DTD/entities, scripts, embedded executable objects, external references including
hyperlinks, DDE sources and WEBSERVICE/HYPERLINK/DDE calls. The converter uses a
private profile and an allowlisted environment with private XDG/temp directories.

These controls are not an OS/filesystem/network sandbox. There is no bundled
public template-upload or hosted execution service. Application data adapters own
query authorization, read-only access, parameter binding, result bounds and
timeouts; model adapters own prompt construction and factual validation.
