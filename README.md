# Report Agent

Report Agent is a Python library and CLI for generating PDF reports from complete
LaTeX templates. The template defines the document structure, JSON/YAML metadata
defines the named inputs and their presentation, and runtime values supply text,
images, charts, and tables.

The project targets recurring business reports with controlled typography,
financial tables, charts, and printable layouts. An optional content resolver
prepares query results and generated summaries through application-owned adapters.

## Rendering model

The placeholder `<<summary>>` maps to `inputs.summary` in metadata and
`summary` in the runtime input mapping. Its content renderer prepares a fragment,
the presentation layer applies its style, and Jinja inserts it into the document.

~~~mermaid
flowchart LR
    Sources[Queries and supplied content] --> Resolver[Optional ContentResolver]
    Resolver --> Inputs[Typed runtime inputs]
    Direct[Caller content] --> Inputs
    Template[Complete TeX template] --> Renderer[ReportRenderer]
    Metadata[JSON / YAML / Python metadata] --> Renderer
    Inputs --> Renderer
    Renderer --> Prepare[Validate, stage, render, style, expand]
    Prepare --> Packages[Check required packages]
    Packages --> Compiler[Compile with texres]
    Compiler --> Result[PDF, artifacts, diagnostics]
~~~

Templates own the preamble, page geometry, static sections, headers, footers, and
placeholder placement. Metadata supplies content options and shared styling.
User and agent text is escaped as plain text. Blank lines preserve paragraphs.

| Metadata type | Python input | Supported content |
| --- | --- | --- |
| `text` | `TextInput(str)` | Plain text with optional defaults and character limits |
| `image` | `ImageInput(Path)` | PNG, JPEG, or PDF |
| `graph` | `GraphInput(Path)` | Existing PNG, JPEG, or PDF chart |
| `graph` | `FigureInput(Figure)` | Live matplotlib Figure exported as vector PDF |
| `table` | `TableInput(DataFrame)` | Native LaTeX tables generated through pandas Styler |

## Setup with uv and a virtual environment

Use Python 3.12 or later and [uv](https://docs.astral.sh/uv/). The repository's
`.python-version` selects Python 3.12 and `uv.lock` records dependency versions.
Run these commands from the repository root.

~~~sh
uv sync --locked
uv run report --help
uv run report version
~~~

`uv sync` creates `.venv` and installs the project and development dependencies.
`uv run` uses that environment automatically. Optional shell activation is
`source .venv/bin/activate`.

PDF generation requires the external [texres compiler](https://github.com/leoliu0/texres)
on `PATH`. Verify it with `texres --version`. Examples and compiler integration
tests have been exercised with texres 0.7.10.

For Parquet input, install the optional extra.

~~~sh
uv sync --locked --extra parquet
~~~

Use `uv run --extra parquet ...` for commands that need to keep the extra
installed. CSV input works with the standard installation.

Poppler's `pdftotext` and `pdfinfo` support PDF inspection and integration
tests. `pdftoppm` renders page previews for visual review.

## Quick start

Render the included plain-text template from the command line.

~~~sh
uv run report render examples/plain_text \
  --metadata examples/plain_text/template.json \
  --text 'title=Quarterly review' \
  --text 'summary=Revenue increased by 12%.' \
  --output output/pdf/review.pdf
~~~

Metadata supplies defaults for the reporting period and notes. The optional
footer can be omitted. Use `template.yaml` in the same directory for equivalent
YAML metadata.

Build the comprehensive example to see images, both graph input forms,
financial tables, heatmaps, grouped rows, and a multi-page appendix.

~~~sh
uv run python examples/comprehensive/render.py
~~~

The result is `output/pdf/comprehensive-report.pdf`. The
[comprehensive walkthrough](docs/comprehensive-example-walkthrough.md) maps each
PDF section to its template, metadata, runtime values, and rendering classes.

## Author a template and metadata

Create `my_report/main.tex` with the following content. Keep bundles focused on
the resources used by the report because their non-hidden files are copied into
the build workspace.

~~~tex
\documentclass[11pt]{article}
\usepackage[margin=25mm]{geometry}
\usepackage{graphicx,booktabs}
\usepackage[table]{xcolor}
\setlength{\parindent}{0pt}
\begin{document}
<<logo>>\par
\section*{<<title>>}
<<summary>>
\subsection*{Revenue by region}
<<sales>>\par
\medskip
<<trend>>\par
\end{document}
~~~

Create `my_report/template.json` to declare those placeholders.

~~~json
{
  "schema_version": 1,
  "id": "quarterly_review",
  "entrypoint": "main.tex",
  "compiler": {
    "engine": "xelatex",
    "table_overflow_tolerance_pt": 2.0
  },
  "inputs": {
    "title": {"type": "text", "max_chars": 120},
    "summary": {
      "type": "text",
      "max_chars": 2000,
      "style": {
        "typography": {"font_size_pt": 11, "line_height_pt": 16},
        "layout": {"display": "block", "space_after_pt": 12}
      }
    },
    "sales": {
      "type": "table",
      "backend": "styler",
      "preset": "financial",
      "precision": 2,
      "show_index": false
    },
    "logo": {"type": "image", "required": false, "width": "20mm"},
    "trend": {"type": "graph", "required": false, "width": "0.9\\linewidth"}
  }
}
~~~

YAML files, Python mappings, and validated `TemplateMetadata` objects share this
schema. Unknown fields, duplicate file mapping keys, and incompatible options
produce validation errors.

Jinja uses `<<...>>` for values, `<%...%>` for statements, and `<#...#>` for
comments. Use `<% include "summary.tex" %>` for a statically named partial
containing dynamic placeholders. Ordinary TeX `\input{...}` resources are
copied and processed by the compiler.

## Python API

This example renders `my_report` with a DataFrame and a live Figure. The logo is
optional and can be omitted.

~~~python
from pathlib import Path

import pandas as pd
from matplotlib.figure import Figure

from report_agent import (
    FigureInput,
    RenderRequest,
    TableInput,
    TextInput,
    create_renderer,
)

figure = Figure(figsize=(6, 3))
axis = figure.subplots()
axis.plot(["Q1", "Q2", "Q3"], [1100, 1250, 1430], marker="o")
axis.set_ylabel("Revenue")

result = create_renderer().render(
    RenderRequest(
        template=Path("my_report"),
        metadata=Path("my_report/template.json"),
        inputs={
            "title": TextInput("Quarterly sales review"),
            "summary": TextInput("Revenue increased by 12% across the period."),
            "sales": TableInput(
                pd.DataFrame({"Region": ["EMEA", "APAC"], "Revenue": [1320.50, 930.25]})
            ),
            "trend": FigureInput(figure),
        },
        output=Path("output/pdf/quarterly-review.pdf"),
    )
)

for issue in result.diagnostics:
    print(issue.severity, issue.stage, issue.code, issue.input_name, issue.message)

if result.pdf_path is None:
    raise SystemExit(1)
print(result.pdf_path)
~~~

Use `Path` objects for template, metadata-file, output, and asset paths.
`RenderRequest.metadata` also accepts a Python mapping or `TemplateMetadata`.

Figure export preserves caller-owned dimensions and axes layout. Drawing may
populate Matplotlib caches. Figures using `usetex=True` must be exported by the
caller and supplied as graph files.

## CLI inputs and manifests

The `report render` command accepts repeated named assignments.

| Option | Value |
| --- | --- |
| `--text` | `NAME=VALUE` |
| `--table` | `NAME=data.csv` or `NAME=data.parquet` |
| `--image` | `NAME=logo.png`, JPEG, or PDF |
| `--graph` | `NAME=trend.pdf`, PNG, or JPEG |
| `--inputs` | JSON or YAML runtime-content manifest |
| `--input-root` | Allowed base directory for referenced asset paths |

For the custom template above, save the following as `my_report/inputs.yaml`.

~~~yaml
inputs:
  title: Quarterly sales review
  summary:
    type: text
    text: Revenue increased by 12% across the period.
  sales:
    type: table
    path: data/sales.csv
~~~

Create `my_report/data/sales.csv`.

~~~csv
Region,Revenue
EMEA,1320.50
APAC,930.25
~~~

~~~sh
uv run report render my_report \
  --metadata my_report/template.json \
  --inputs my_report/inputs.yaml \
  --input-root my_report \
  --text 'title=Reviewed quarterly sales' \
  --output output/pdf/quarterly-review.pdf
~~~

To add existing assets, use descriptors such as
`logo: {type: image, path: assets/logo.png}` and
`trend: {type: graph, path: assets/trend.pdf}` inside the manifest's `inputs`
mapping. Create the referenced files before using those entries. JSON manifests
use the same fields.

Manifest paths resolve relative to the manifest file. Explicit flag paths resolve
relative to the working directory. Explicit flags override manifest values,
and duplicate names across explicit flags are rejected.

For agent-created manifests, `--input-root` restricts referenced asset paths to
an allowed directory after resolving parent traversal and symlinks. Python
applications can use `InputFileLoader(base_directory=...)` for the same check.
The local CLI permits arbitrary asset paths when that option is omitted.
The restriction assumes the allowed filesystem stays stable during the build.

The CLI prints diagnostics to stderr and the completed PDF path to stdout.
Rendering failures exit with status 1. Invalid arguments exit with status 2.
Live Figure inputs enter through the Python API.

## Content and presentation options

| Field | Meaning and default |
| --- | --- |
| `required` | Whether a value must be supplied, default `true` |
| `default` | Optional text fallback |
| `max_chars` | Positive text character limit, required for agent inputs |
| `visible` | Whether content appears in the template, default `true` |
| `width` | Image/graph width, default `1\linewidth` |
| `backend` | Table strategy, currently `styler` |
| `preset` | `financial`, `comparison`, `heatmap_sequential`, or `heatmap_diverging` |
| `precision` | Optional 0–8 decimal places for non-integral numeric values |
| `show_index` | Whether table index labels appear, shown by default |
| `longtable` | Use a table that can paginate vertically |
| `style` | Shared typography, block layout, heading, and container settings |

Omitted precision preserves numeric display precision. Integer counts retain
integer formatting. Tables support escaped labels/cells, MultiIndex headers and
row groups, and missing values displayed as `--`. Heatmaps require numeric
columns and finite usable data. Colored presets require unique row/column labels.

Every content type uses `inputs.<name>.style`. Supported settings include font
size, leading, paragraph spacing, color, bold/italic, alignment, headings,
spacing, page transitions, and bordered background boxes. Paragraph and container
settings require `layout.display: block`. Empty optional content emits an empty
fragment.

`longtable: true` lets TeX use the available page space and continue on later
pages with repeated headers. Place it in breakable document flow. Box containers
use an unbreakable minipage and must fit on one page. Metadata rejects a boxed
longtable.

Landscape pages and sideways tables are template-controlled. Automatic column
splitting, wrapping policies, and orientation selection are planned features.
See the [style guide](docs/placeholder-styles.md) and
[table layout proposal](docs/table-layout-design.md).

## Query and agent content resolution

`ContentResolver` prepares typed inputs before rendering. It fetches query-backed
tables first, then generates text whose `uses` list references those tables.
Applications provide the following interfaces.

| Interface | Application responsibility |
| --- | --- |
| `DataSource.fetch(QuerySource) -> DataFrame` | Validate and execute a query through a named connection with read-only access, bound parameters, server-side limits, and timeouts |
| `AgentTextGenerator.generate(GenerationRequest) -> str` | Call a generator using its prompt, permitted summaries, character limit, and retry feedback |

A context-only table and dependent summary can be declared as follows.

~~~json
{
  "id": "resolved_review",
  "inputs": {
    "raw_sales": {
      "type": "table",
      "visible": false,
      "summary_head_rows": 5
    },
    "summary": {
      "type": "text",
      "source": "agent",
      "prompt": "Summarize the supplied sales results",
      "uses": ["raw_sales"],
      "max_chars": 1200
    }
  }
}
~~~

This template needs a `<<summary>>` placeholder. Hidden inputs must be referenced
by an agent's `uses`, and the renderer skips their conversion and asset staging.

Query bindings use `QuerySource(connection=..., query=..., params=..., row_limit=...)`.
Adapters must apply the result bound before fetching, for example through a
validated SQL `LIMIT row_limit + 1`. The resolver also rejects fetched results
that exceed the limit.

Generators receive counts and bounded column profiles with non-null counts and
finite numeric min/max/mean. Setting `summary_head_rows` opts into sending raw
cell data. Requested leading rows are limited to 20, text cells to 200 characters,
and columns to `summary_max_columns`, default 20.

All row samples in a generation request share `summary_max_row_chars`, default
8,192 compact JSON characters. Complete rows are retained in `uses` order,
with omission counts for budget truncation. Use deterministic pre-aggregated
results when generated claims depend on categories or trends.

`GenerationRequest` includes `max_chars`. Overlong output gets one retry with
feedback. A second invalid response returns `resolution_failed` and reports
that the retry was used. Supplied text can override generation.

Check `ResolutionResult.diagnostics` before passing its `inputs` to
`RenderRequest`. Live database/model adapters are extension work.
The [resolver guide](docs/content-resolution.md) provides contracts and wiring.

## Compilation, artifacts, and diagnostics

Each build validates input/template compatibility, copies resources into a
private workspace, renders content, expands Jinja, checks package declarations,
and compiles the complete document. The texres adapter has a 120-second default
timeout and stops the process group on supported systems when compilation times
out or is cancelled.

XeLaTeX is the default engine. Metadata also accepts pdfLaTeX and LuaLaTeX.
pdfLaTeX requires compatible text and template fonts. XeLaTeX/LuaLaTeX with
appropriate fonts support broader character coverage.

Templates must load the packages their generated content needs.

| Feature | Required declarations |
| --- | --- |
| Images and graphs | `graphicx` |
| Native table rules | `booktabs` |
| Merged table row labels | `multirow` when emitted |
| Paginated tables | `longtable` |
| Typography colors and boxes | `xcolor` |
| Colored table cells | `xcolor` and `colortbl`, commonly supplied by `\usepackage[table]{xcolor}` |

The scanner follows literal declarations and local TeX/class/style dependencies
in source order, including forwarded options before the first `xcolor` load.
For packages loaded through external classes or macro logic, template authors
can assert `provided_packages: ["graphicx", "booktabs"]` in metadata.
See the [package contract](docs/review-hardening.md) for scanner limits.

Attributed table width overflow up to `compiler.table_overflow_tolerance_pt`,
default 2pt, produces a warning. Larger reported width prevents PDF publication.
Zero makes every positive reported overflow an error. The tolerance classifies
compiler diagnostics.

Successful output has the following layout.

~~~text
output/pdf/
  quarterly-review.pdf
  quarterly-review.artifacts/
    main.tex
    compile.log
    report-assets/
      <content-hash>.pdf
~~~

Nested template paths are preserved. `RenderResult` contains the PDF path,
structured diagnostics, and retained artifact paths. Diagnostics carry
`stage`, `code`, `message`, `severity`, and an input name when applicable.

| Typical diagnostic | What to check |
| --- | --- |
| `missing_input`, `input_type`, `text_length` | Runtime values and metadata declarations |
| `unused_input`, `undeclared_placeholder`, `hidden_placeholder` | Template names and visibility |
| `unsupported_backend` | Registered renderer and backend |
| `missing_package` | Template preamble or `provided_packages` |
| `table_overflow` | Table width, template placement, tolerance |
| `compiler_not_found`, `compiler_timeout`, `compiler_failed` | texres installation and retained log |
| `internal_error` | Diagnostic stage and application traceback logs |

Compiler failures retain available source, assets, and logs while preserving a
previous destination PDF. Early validation failures may return diagnostics before
artifacts exist. Output and artifact paths are checked against template resources
to prevent accidental replacement. Files use atomic replacement, and the
workspace is cleaned after the call.

Templates are trusted TeX sources. Escaping, sandboxed Jinja, and disabled shell
escape protect specific rendering boundaries. Untrusted template uploads require
a separately enforced process/filesystem isolation boundary.

Concurrent jobs should use distinct output paths. Artifacts are published as
individual files, and calls targeting the same destination require application
coordination. Concurrent matplotlib rendering and service throughput have not
been established by the sequential benchmark.

## Package architecture

The code uses a `src/` layout, typed value objects, protocol interfaces, and
constructor injection. `create_renderer()` composes the default collaborators.

| Package | Main responsibility |
| --- | --- |
| `application` | `RenderRequest`, `ReportRenderer`, preflight validation, composition |
| `models` | Typed inputs, template/context values, diagnostics, results |
| `metadata` | Schemas, style/dimension validation, JSON/YAML parsing |
| `templates` | Bundle discovery, dependency inspection, Jinja expansion |
| `rendering` | Text, image, graph, table strategies selected by type/backend |
| `presentation` | Shared scoped styling for every placeholder |
| `validation` | Shared text policy and package scanning |
| `compilation` | Compiler protocol, texres lifecycle, overflow diagnostics |
| `resolution` | Query bindings, bounded summaries, generated-text requests |
| `storage` | Temporary workspaces and artifact publication |
| `interfaces.cli` | Typer commands and file-backed content loading |

Replaceable boundaries include `ContentRenderer`, `TemplateEngine`,
`TemplateRepository`, `LatexCompiler`, `PlaceholderStyler`,
`WorkspaceManager`, and `ArtifactStore`. Renderer registration uses
`(type, backend)` keys. Styler is the bundled table implementation. The schema
recognizes `great_tables` for a future adapter, and selecting it currently
returns `unsupported_backend`.

The [architecture reference](docs/project-overview.md) provides a package tree,
class responsibilities, dependency direction, and build lifecycle.

## Examples and documentation

| Example | Demonstrates | Command |
| --- | --- | --- |
| [Plain text](examples/plain_text/render.py) | Defaults, optional values, escaping | `uv run python examples/plain_text/render.py` |
| [Comprehensive](examples/comprehensive/README.md) | Seven pages, charts, six tables, heatmaps, appendix | `uv run python examples/comprehensive/render.py` |
| [Rotated tables](examples/rotated_tables/README.md) | Landscape page and sideways table | `uv run python examples/rotated_tables/render.py` |
| [Placeholder styles](examples/placeholder_styles/README.md) | Typography, headings, alignment, containers | `uv run python examples/placeholder_styles/render.py` |

Generated reports and assets go under `output/`. The walkthrough includes
committed page previews for the comprehensive example.

- [Comprehensive walkthrough](docs/comprehensive-example-walkthrough.md)
- [Placeholder styling](docs/placeholder-styles.md)
- [Content resolver](docs/content-resolution.md)
- [Package checks, input manifests, and overflow behavior](docs/review-hardening.md)
- [Proposed table layout configuration](docs/table-layout-design.md)

## Development and benchmarks

~~~sh
uv run --extra parquet ruff check .
uv run --extra parquet ruff format --check .
uv run --extra parquet pytest -q
uv build
~~~

Unit tests cover schemas, escaping, registry selection, styles, resolver
ordering/retries/budgets, path restrictions, publication, and compiler failures.
Integration tests compile PDFs, inspect text and pagination, exercise file/Figure
inputs, and verify package/overflow behavior. Compiler tests skip when texres or
the required Poppler tools are unavailable. The Parquet loader test skips when
its optional dependency is absent.

Measure current sequential build times with the benchmark runner.

~~~sh
uv run python benchmarks/report_generation.py --runs 10
~~~

Results go to `output/benchmarks/report-generation.json`. They include input
preparation and rendering as separate timings, one first request, and subsequent
measured requests. The [benchmark guide](benchmarks/README.md) documents
measurement boundaries and a historical baseline.

## Repository hygiene and license

Version-controlled files include source/tests, TeX templates, JSON/YAML example
metadata, documentation and its page previews, `uv.lock`, and project definitions.

`.gitignore` excludes environments, caches, local secrets, local editor/agent
settings, generated output, `*.artifacts/` directories, package builds, and TeX
intermediates. Keep actual template resources and documentation images under
version control. Store private runtime data outside bundles and write generated
reports under `output/`.

Report Agent is available under the [MIT license](LICENSE).
