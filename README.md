# Report Agent

Generate PDF, DOCX, XLSX and PPTX reports from reusable templates and typed runtime
content. Templates own document structure and design; application inputs provide
text, images, Matplotlib charts and pandas tables. An optional injected resolver
fetches data and generates summaries or animations during the normal render call.

| Output | Template | Metadata | Engine |
| --- | --- | --- | --- |
| PDF | Complete LaTeX (`.tex`) | Schema v1 | texres |
| DOCX | Flat OpenDocument Text (`.fodt`) | Schema v2 | LibreOffice Writer |
| XLSX | Flat OpenDocument Spreadsheet (`.fods`) | Schema v2 | LibreOffice Calc |
| PPTX | Flat OpenDocument Presentation (`.fodp`) | Schema v2 | LibreOffice Impress |

Office output is experimental. Native tables, document sections, named workbook
tabs, formulas and embedded animated GIFs are supported. Final layout and animation
playback need review in the recipient's Office application. See the
[Office compatibility reference](docs/office-reports.md).

## Installation

Use Python 3.12 or later and [uv](https://docs.astral.sh/uv/). From the repository root:

```sh
uv sync --locked
uv run report --help
```

Install the external engine for the formats you use:

- PDF: [texres](https://github.com/leoliu0/texres) on `PATH`; verify with
  `texres --version`. Local integration checks have used version 0.7.10.
- Office: LibreOffice with `soffice` on `PATH`; verify with `soffice --version`.
  The [template guide](docs/libreoffice-template-guide.md#10-configure-libreoffice-and-inspect-results)
  also shows how to configure an explicit executable path.
- Install the fonts used by your templates. Poppler supplies `pdftotext`,
  `pdfinfo` and `pdftoppm` for PDF inspection and example previews.

CSV input is included. For Parquet, use `uv sync --locked --extra parquet` and
retain the extra with `uv run --extra parquet ...`.

## Quick start

Generate a PDF from the included template:

```sh
uv run report render examples/plain_text \
  --metadata examples/plain_text/template.yaml \
  --text 'title=Quarterly review' \
  --text 'summary=Revenue increased by 12%.' \
  --output output/pdf/review.pdf
```

Generate the comprehensive Office examples:

```sh
uv run python examples/office_comprehensive/render.py
# Work on one format:
uv run python examples/office_comprehensive/render.py --only pptx
```

Outputs appear in `output/office_comprehensive/`: a document with portrait and
landscape sections, a nine-slide deck with an animated chart, and a seven-tab
workbook with calculated summaries. Follow the
[LibreOffice template tutorial](docs/libreoffice-template-guide.md) to import a
branded DOCX, preserve headers/footers, add slots and supply your own data.

## Python API

```python
from pathlib import Path

from report_agent import RenderRequest, TextInput, create_renderer

bundle = Path("examples/plain_text")
result = create_renderer().render(
    RenderRequest(
        template=bundle,
        metadata=bundle / "template.yaml",
        inputs={
            "title": TextInput("Quarterly review"),
            "summary": TextInput("Revenue increased by 12%."),
        },
        output=Path("output/pdf/review.pdf"),
    )
)
for issue in result.diagnostics:
    print(issue.severity, issue.stage, issue.code, issue.input_name, issue.message)
if result.output_path is None:
    raise SystemExit(1)
print(result.output_path)
```

The same API dispatches schema-v2 metadata to LibreOffice. Use `Path` objects for
files; metadata also accepts a mapping or validated model. `output_path` applies
to every format; `pdf_path` remains a compatibility alias for PDF output.

| Runtime value | Content |
| --- | --- |
| `TextInput(str)` | Plain text, escaped and validated; template controls formatting |
| `TableInput(DataFrame)` | Native report table; an entire data tab in Calc |
| `ImageInput(Path)` | Image file; Office accepts PNG/JPEG, PDF also accepts PDF images |
| `GraphInput(Path)` | Existing chart image; same format restrictions |
| `FigureInput(Figure)` | Live Matplotlib figure; exported as PDF for TeX or PNG for Office |
| `AnimationInput(gif_path, poster_path)` | Animated GIF embedded in PPTX |

Office slots use XML names such as `<ra:text name="summary"/>`; LaTeX uses
`<<summary>>`. Both match `inputs.summary` in metadata and `"summary"` at runtime.
Office styles live in Flat ODF; LaTeX also supports per-input presentation metadata.

## CLI inputs and resolution

`report render` accepts repeated `--text NAME=VALUE`, `--table NAME=CSV_OR_PARQUET`,
`--image NAME=PATH`, `--graph NAME=PATH` and `--animation NAME=GIF_PATH` flags.
`--inputs inputs.yaml` accepts a JSON/YAML content manifest. Manifest asset paths
are relative to that file; explicit flag paths are relative to the working
directory. Explicit flags override manifest values. `--input-root DIRECTORY`
restricts referenced asset paths.

For query-backed data or generated content, inject
`create_renderer(resolver=ContentResolver(...))` and supply query bindings through
`RenderRequest.queries`. The renderer resolves tables, agent text and animations
before backend validation and keeps generated media alive through conversion.
Application adapters own database access and model/generator implementations.
Missing adapters return resolution diagnostics; supplied values override generation.

The CLI exposes the same flow through `--resolver myapp.reports:create_resolver`
and `--queries queries.yaml`. The factory must be importable, take no arguments
and return `ContentResolver`. It is explicit trusted application code, never a
module selected by a template. See the [resolver guide](docs/content-resolution.md)
for complete Python and CLI wiring, query bounds and generated-text contracts.

## Artifacts and failures

A report has a sibling `<output-stem>.artifacts/` directory containing expanded
source, available logs and staged assets; Office builds also retain `build.json`
and the engine version. Publication replaces the artifact snapshot instead of
accumulating files from old runs. Failed conversions preserve the previous final
report and attempt to retain current diagnostic artifacts. Check the returned
result, since an old output file can still exist after a failed build.

Use distinct output stems for concurrent jobs, including across formats. Templates
are trusted source files; validation and private profiles are not a sandbox for
untrusted uploads. Details are in the [PDF checks guide](docs/review-hardening.md)
and [Office contracts](docs/office-reports.md).

## Examples and documentation

| Start here | Details |
| --- | --- |
| [LibreOffice template tutorial](docs/libreoffice-template-guide.md) | Import designs, add slots, render through Python/CLI, troubleshoot |
| [Office XML authoring reference](docs/office-template-authoring.md) | Page styles, slide frames, workbook tabs and table styling |
| [Office backend contracts](docs/office-reports.md) | Supported limits, animation, configuration and compatibility status |
| [Comprehensive Office examples](examples/office_comprehensive/README.md) | Shared data across DOCX, PPTX and XLSX |
| [Comprehensive PDF walkthrough](docs/comprehensive-example-walkthrough.md) | Full LaTeX template, charts, styled tables and paginated appendix |
| [Placeholder style guide](docs/placeholder-styles.md) | LaTeX typography, boxes, headings and page transitions |
| [Content resolution](docs/content-resolution.md) | Query adapters, agent summaries, generators and CLI configuration |
| [Project architecture](docs/project-overview.md) | Packages, collaborators and build lifecycle |
| [PDF validation](docs/review-hardening.md) | Package declarations, input manifests and overflow behavior |
| [Benchmarks](benchmarks/README.md) | Sequential report generation measurements |

Small runnable Office examples live in `examples/office_docx`, `office_xlsx` and
`office_pptx`; each contains a complete template, metadata and `render.py`.
PDF examples also include `examples/plain_text`, `placeholder_styles` and
`rotated_tables`.

## Development

```sh
uv run --extra parquet ruff check .
uv run --extra parquet ruff format --check .
uv run --extra parquet pytest -q
uv build
```

Office integration tests perform actual LibreOffice conversions. Each Office
build records its engine version in the retained artifacts. PDF integration tests
skip when texres or required Poppler tools are absent; run locally with those
dependencies for full PDF coverage.

Generated reports, caches, environments and `.artifacts` directories are ignored.
Keep reusable templates and their static resources in version control; runtime
private data belongs outside template bundles. Report Agent uses the [MIT license](LICENSE).
