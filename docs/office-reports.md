# Office reports with LibreOffice

The experimental Office backend accepts complete styled Flat OpenDocument XML
sources: FODT for DOCX, FODS for XLSX, and FODP for PPTX. The existing LaTeX/PDF
backend remains the schema-v1 default. No Office libraries or running desktop
session are needed for PDF generation.

Start with the [step-by-step template guide](libreoffice-template-guide.md) for
installation, importing a branded Word sample, adding slots, Python/CLI usage,
pages, slides, tabs and troubleshooting. This page describes backend contracts
and verification status.

Install the Python project normally and install LibreOffice separately. `soffice`
must be available on PATH. Development verification currently uses the available
LibreOfficeDev 26.8 build; a released-version baseline and desktop Microsoft Office
compatibility checks remain outstanding. Every Office result carries a warning
and a build manifest marking that status. Package verification does not establish
identical Word, Excel, or PowerPoint rendering.

For complete templates demonstrating page styles, portrait/landscape section
breaks, explicit slides, named tabs, cross-tab formulas and a generated animation,
see the [comprehensive examples](../examples/office_comprehensive/README.md) and
[template authoring guide](office-template-authoring.md).

## Run the examples

```sh
uv run python examples/office_docx/render.py
uv run python examples/office_xlsx/render.py
uv run python examples/office_pptx/render.py
```

The animation example also runs through the CLI with its application resolver
factory and query bindings. From the repository root, `python -m` makes the
example module importable:

```sh
uv run python -m report_agent render examples/office_pptx \
  --metadata examples/office_pptx/template.yaml \
  --resolver examples.office_pptx.render:create_resolver \
  --queries examples/office_pptx/queries.yaml \
  --output output/office/cli-animated-sales.pptx
```

Outputs go under `output/office/`. Each has a sibling `.artifacts` directory with
expanded XML, a build manifest, staged assets, and the conversion log. Artifacts
are published as a replacement snapshot, removing files from earlier runs.
Failure preserves the previous output and attempts to retain current expanded
source/logs; retention failures are separate warnings and preserve the original
conversion diagnostic. Use distinct
output stems for concurrent reports, including different formats.

The PPTX example injects a sample data source through `ContentResolver`, fetches a
bounded DataFrame, runs a registered Matplotlib generator in an owned process,
exports a finite animated GIF and PNG poster, and embeds the GIF into the final
PPTX. The source template is FODP. Only the resulting PPTX is needed by recipients;
Python and data access run during report construction.

## Templates and metadata

Metadata uses `schema_version: 2`, an explicit `document.engine: libreoffice`,
`document.format`, and an entrypoint matching that format. See the example YAML
files. The output suffix must agree with the metadata. Unknown settings and TeX
presentation fields are rejected.

Flat XML owns styles and layout. XML slots use the namespace
`urn:report-agent:template:1`, conventionally bound to `ra`:

- `ra:text name="title"` inserts inline plain text in a paragraph or heading.
- `ra:paragraphs name="summary" style-name="Body"` inserts Writer paragraphs.
- `ra:table name="sales"` creates a native table. In Calc it creates a dedicated
  sheet; `sheet-name`, `max-rows`, and `max-columns` control its name and capacity.
  Tables use single-level headers and preserve data types and row/column order.
- `ra:cell name="label"` inserts literal text within a template-authored Calc cell.
- `ra:image name="trend" width="15cm" height="7cm"` inserts a contained PNG/JPEG or
  `FigureInput` exported to PNG. Writer slots belong inside paragraphs; Impress
  image slots belong directly in a slide and have `x`/`y` coordinates.
- `ra:animation name="sales_animation" x="2cm" y="2cm" width="24cm" height="12cm"`
  embeds an animated GIF in an Impress slide. The supported playback contract is
  automatic, looping GIF playback, subject to target-viewer verification.

Templates may refer to their own ODF styles using `style-name` for paragraphs and
`table-style-name`, `header-cell-style-name`, and `body-cell-style-name` for tables.
Physical image dimensions use cm, mm, in, or pt. Runtime text is serialized as XML
text; it is never executable markup. Empty optional slots disappear. Design the
base file in LibreOffice, save Flat XML, then add slots in a text editor; visual
re-editing is not guaranteed to preserve custom slot elements.

Calc supports template-authored formulas. Text starting with `=` stays text.
Numbers exceeding reliable Excel integer precision, nonfinite values, and
ambiguous timezone-aware dates fail explicitly. Table slots create complete
sheets rather than inserting rows into an existing formula region. Dynamic
reference rewriting and editable native charts are outside the current subset.
Formula evaluation uses Calc's conversion; SUM, COUNTA and arithmetic fixtures establish
only that tested subset, not full Excel function compatibility. Source formula
caches are cleared before conversion so results use runtime data, including
references to later tabs.

## Animation generation

Declare a v2 `animation` input with `source: generator`, a registered `generator`
name, table dependencies in `uses`, and bounded `export` options. The example YAML
shows the full contract. The generator receives copied DataFrames and returns a
finite Matplotlib `Animation` with exactly `ceil(fps * duration_seconds)` frames.
Pass the resolver to `create_renderer(resolver=...)` and query bindings to
`RenderRequest.queries`. The normal render path owns generated media until
conversion finishes. Explicit resolution remains supported; that interface
requires the caller to keep its media workspace alive until rendering finishes.

The animation registry currently requires a dedicated single-threaded macOS/Linux
rendering worker and uses an owned forked child. It enforces timeouts and kills
owned encoder descendants on cancellation. GIF generation has a conservative
512 MiB decoded-frame budget in addition to limits of 30 seconds, 30 fps, 900
frames, 1920x1080 pixels, and 50 MiB encoded bytes. A deck has a 100 MiB animation
media budget. Requests exceeding a limit fail instead of truncating content.

`AnimationInput(path, poster_path)` also accepts pre-generated GIF files. File
manifests and `--animation NAME=PATH` accept an animation file; the first frame is
used to stage a PNG poster when the file is also passed as its poster. Static
`FigureInput` behavior is unchanged.

Matplotlib generation can export H.264 MP4 when FFmpeg is installed, but the
current FODP-to-PPTX insertion path accepts GIF only. MP4 insertion, on-click start,
and native PowerPoint object effects are explicitly unsupported. GIF was selected
because the local export spike preserved its original bytes and frames. Playback
in a named desktop PowerPoint version remains unverified; web support is separate.

The build verifies package relationships and requires the original GIF in the
PPTX media package. A flattened or lost animation fails the build. PDF previews
cannot establish motion or playback. The poster is retained for static previews;
no automatic preview-PDF generation is currently exposed.

## Application configuration

```python
from report_agent import create_renderer
from report_agent.backends.libreoffice import LibreOfficeBackend
from report_agent.compilation.libreoffice import LibreOfficeConverter

renderer = create_renderer(
    office_backend=LibreOfficeBackend(
        converter=LibreOfficeConverter(
            executable="/Applications/LibreOffice.app/Contents/MacOS/soffice",
            timeout_seconds=120,
        )
    )
)
```

Each conversion has a private user profile, source/export directories, captured
logs, and bounded process lifetime. Version probing is cached per converter
instance, including across repeated calls on one renderer. The subprocess
environment permits PATH, locale/timezone and Windows system-directory settings;
XDG and temporary paths point into the private workspace. HOME and unrelated
application environment variables are not forwarded.

Templates remain trusted inputs. External links (including hyperlinks),
DTD/entities, scripts, embedded executable objects, DDE sources and calls to
WEBSERVICE/HYPERLINK/DDE are unsupported. These checks and environment filtering
do not replace process/filesystem/network isolation for hosted untrusted uploads.

## Verification status

Office integration tests perform real exports, and each build retains its
LibreOffice version. Color assertions ignore hexadecimal case. PDF integration
tests skip if texres is unavailable; run them locally with texres installed.

Automated checks cover schema validation, XML escaping and data types, slot
compatibility, output protection, conversion failures, formula cached results,
concurrent private profiles, and data-to-GIF-to-PPTX package preservation. They
also check that the PPTX contains its animation after removing the resolution
workspace. The full legacy PDF suite remains part of regression testing.

Before production support is declared, pin a released LibreOffice and font set,
review the native Office outputs in the target apps, and play the final PPTX in
Slide Show mode after moving it away from its source assets. Record viewer OS and
version, looping/start behavior, and visual fit. No desktop PowerPoint playback
claim is made by the package tests.

## Local implementation checks (November 13, 2026)

The implementation branch passed 216 tests, Ruff lint/format checks, and a wheel /
source distribution build. Real conversion tests include native DOCX content and
figure embedding, concurrent private profiles, XLSX formula cached values, and a
query-generated GIF retained in a portable PPTX package.

`benchmarks/office_generation.py --runs 3` measured 100-row report preparation,
conversion, verification, and publication at 0.80–0.84 seconds per DOCX and
0.797–0.803 seconds per XLSX in this development environment. These measurements
exclude previews and animation encoding and are not production capacity targets.
Raw measurements are written under `output/benchmarks/office/`.

Desktop PowerPoint was detected locally, but Computer Use was not approved to
control the app. The attempted Slide Show verification could not proceed; playback
remains unverified. No alternative UI-control mechanism was used.
