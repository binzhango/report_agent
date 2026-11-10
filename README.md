# Report Agent

Render complete LaTeX templates into PDF reports using JSON or YAML
config/metadata and content passed at render time: text, images, graphs, and tables.
Python callers can also pass metadata and content directly as objects.

## Development setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12 or later. The
`.python-version` file selects Python 3.12 for local development.

```sh
uv sync --locked
uv run report --help
uv run report version
```

Install [texres](https://github.com/leoliu0/texres) and put it on `PATH` to build
PDFs. The initial end-to-end example was verified with texres 0.7.10. Python
dependencies and development tools are managed by uv; the compiler is external.

## Render a report

Build the comprehensive seven-page example with images, graphs, financial tables,
heatmaps, grouped rows, and a multi-page appendix:

```sh
uv run python examples/comprehensive/render.py
```

The PDF is saved to `output/pdf/comprehensive-report.pdf`. See the
[example guide](examples/comprehensive/README.md) for the capability-to-report map.
The [detailed walkthrough](docs/comprehensive-example-walkthrough.md) maps every
PDF section to its template, metadata, runtime inputs, and rendering classes.
The [rotated-table example](examples/rotated_tables/README.md) demonstrates a
landscape page and a sideways table on a portrait page.
The [placeholder styles example](examples/placeholder_styles/README.md) shows
how `inputs.<name>.style` in JSON/YAML controls typography, section headings,
spacing, alignment, page transitions, and containers for each placeholder.

For a minimal plain-text example:

```sh
uv run python examples/plain_text/render.py
```

Or supply text from the command line:

```sh
uv run report render examples/plain_text \
  --metadata examples/plain_text/template.json \
  --text 'title=Quarterly review' \
  --text 'summary=Revenue increased by 12%.' \
  --output output/pdf/review.pdf
```

The CLI also accepts `--table name=data.csv`, `--image name=logo.png`,
`--graph name=trend.pdf`, and `--inputs content.json` or `content.yaml`.
See the [input manifest and review changes](docs/review-hardening.md). For Parquet
tables, install the optional extra with `uv sync --extra parquet`.

Use `template.yaml` for the equivalent YAML metadata. Python callers may pass
a mapping or `TemplateMetadata` directly instead of a metadata path.

The renderer preserves the original template, builds in a temporary workspace,
and publishes the PDF with generated source and logs in `<report>.artifacts/`
beside it. A failed build returns structured diagnostics and leaves any previous
PDF unchanged. Keep the template bundle limited to intended report resources;
non-hidden files are staged into the workspace, and symlinks are rejected.

Plain-text values escape LaTeX special characters. Blank lines separate
paragraphs; a single newline acts as a space. Template layout controls wrapping.
For dynamic partials, use static Jinja includes such as
`<% include "summary.tex" %>`. TeX `\input` files are copied as static resources.

`uv sync` creates and installs the project into `.venv`, including development
dependencies. `uv run` uses that environment automatically. To activate it in
your shell instead:

```sh
source .venv/bin/activate
```

## Development checks

For measured PDF-generation timings and a repeatable runner, see the
[benchmark guide](benchmarks/README.md).

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

Tests cover metadata equivalence, template binding, escaping, validation,
workspace cleanup, and compiler failures. Integration tests build real PDFs and
check extracted text when texres and `pdftotext` are available; otherwise they skip.

## Project layout

```text
src/report_agent/
  __init__.py       # Public ReportRenderer API and typed inputs
  application/      # Render use case, validation, and dependency composition
  models/           # Input, template, diagnostic, and result objects
  metadata/         # Shared schema and JSON/YAML parser strategies
  templates/        # Template repository and expansion interfaces
  rendering/        # Text, image, graph, and table strategies
  presentation/     # Shared per-placeholder typography, sections, and containers
  compilation/      # Compiler interface and texres adapter
  validation/       # Shared text policy and package-declaration checks
  resolution/       # Optional data-source and agent-text interfaces
  storage/          # Workspace and artifact-store interfaces
  interfaces/cli/   # report command
pyproject.toml      # Package metadata, dependencies, and tooling
uv.lock            # Locked dependency versions
```

## Current scope

Whole-template PDF rendering supports typed plain text, PNG/JPEG/PDF assets,
existing graph files, live matplotlib figures, and pandas DataFrames. Tables
support financial/comparison presets, sequential/diverging heatmaps, multi-index
labels, missing values, precision, hidden indices, and multi-page `longtable`.
Graphics dimensions are validated and staged under generated filenames.
JSON/YAML metadata, defaults, optional inputs, Jinja expansion, texres compilation,
and retained source/logs/assets share one pipeline. The CLI currently exposes
text and file-backed inputs; the Python API accepts all content types. Database/agent
adapters, automatic wide/landscape layouts, and Great Tables remain future work.

The optional [content resolver](docs/content-resolution.md) provides interfaces
for application-owned data sources and text generators, without live database or
model clients. Templates are checked for required packages before compilation,
and attributed table overflow fails the build rather than publishing a clipped PDF.

User and agent text is plain text only. The pipeline escapes LaTeX special
characters, and template/metadata presentation controls formatting. Markdown and raw
LaTeX in text fields will not be interpreted.

XeLaTeX is the default engine. pdfLaTeX remains supported for compatible templates
and text, including literal `<`, `>`, and `|`; it does not support arbitrary Unicode.
Use XeLaTeX/LuaLaTeX with suitable template fonts for broader character coverage.

See the [project overview](docs/project-overview.md) for package and class
responsibilities, object collaboration, and dependency direction. The
[table layout proposal](docs/table-layout-design.md) describes planned horizontal
and vertical layout policies separately from implemented behavior.
