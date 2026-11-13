# Authoring Office templates

New to this workflow? Start with the [LibreOffice template guide](libreoffice-template-guide.md)
for an end-to-end tutorial, including reusing an existing branded DOCX. This page
provides the detailed XML authoring reference.

Use a complete Flat OpenDocument XML file to define the document's design and
static structure. Report Agent fills named XML slots and LibreOffice exports the
result to the requested Office format. The comprehensive examples use the same
synthetic business data as the comprehensive LaTeX report.

```sh
uv run python examples/office_comprehensive/render.py
# Build one format while working on its layout:
uv run python examples/office_comprehensive/render.py --only pptx
```

The source files to edit are:

| Output | Complete template | What establishes structure |
| --- | --- | --- |
| DOCX | `examples/office_comprehensive/docx/main.fodt` | Page layouts, master pages, paragraph styles, document flow |
| PPTX | `examples/office_comprehensive/pptx/main.fodp` | Ordered `draw:page` elements, with positioned frames |
| XLSX | `examples/office_comprehensive/xlsx/main.fods` | Ordered `table:table` elements and sheet-producing `ra:table` slots |

Each directory also has `template.yaml` declaring the inputs. `data.py` prepares
values and figures; `render.py` selects the inputs and invokes the backend. The
layout belongs to XML. It is not created by a hidden Python layout builder.

## Common structure and namespaces

The complete files declare namespaces on `office:document`. The snippets below
omit those declarations; copy the example's root when starting a new template.

```xml
<office:document ... office:version="1.3"
    office:mimetype="application/vnd.oasis.opendocument.presentation">
  <office:font-face-decls>...</office:font-face-decls>
  <office:styles>...</office:styles>
  <office:automatic-styles>...</office:automatic-styles>
  <office:master-styles>...</office:master-styles>
  <office:body>
    <office:presentation>...</office:presentation>
  </office:body>
</office:document>
```

Use `office:text` and the text MIME type for Writer, or `office:spreadsheet` and
the spreadsheet MIME type for Calc. `ra` must map to
`urn:report-agent:template:1`. `ra` slots are Report Agent instructions and are
removed before LibreOffice receives the expanded document.

For these examples, put Writer paragraph styles in `office:styles`; put table,
cell and column styles in `office:automatic-styles`. Impress paragraph/frame
styles and Calc cell/column styles also go in `office:automatic-styles`. Impress
native tables use an additional named table template with its referenced cell
styles in `office:styles`, as shown below. The
placement matters: a well-formed XML file can still lose its intended formatting
when a style is declared in the wrong section for the document component.

Names are references, not CSS classes. An attribute such as
`text:style-name="SlideTitle"` points to an ODF style with that exact name.
Define fonts and sizes explicitly instead of relying on application defaults.

## DOCX pages and sections

A Writer document is flowing content. There is no one-XML-element-per-page rule.
A page layout defines the page size and margins, a master page binds that layout
to headers/footers, and a paragraph style can request a page break and select a
master page. This is comparable to LaTeX geometry, page styles and explicit page
breaks. Text and long tables still paginate as their content grows.

### Define paper size and margins

Inside `office:automatic-styles`:

```xml
<style:page-layout style:name="PortraitLayout">
  <style:page-layout-properties
      fo:page-width="21cm" fo:page-height="29.7cm"
      fo:margin-left="1.9cm" fo:margin-right="1.9cm"
      fo:margin-top="1.7cm" fo:margin-bottom="1.7cm"
      style:print-orientation="portrait"/>
</style:page-layout>
```

The comprehensive template also defines `LandscapeLayout`, with width `29.7cm`
and height `21cm`. Usable width is paper width minus the left and right margins;
headers, footers and paragraph spacing also consume page space.

### Bind the layout to a master page

Inside `office:master-styles`:

```xml
<style:master-page style:name="Portrait"
                   style:page-layout-name="PortraitLayout">
  <style:header>
    <text:p text:style-name="Small">NORTHSTAR QUARTERLY BUSINESS REVIEW</text:p>
  </style:header>
  <style:footer>
    <text:p text:style-name="Small">
      Page <text:page-number text:select-page="current">1</text:page-number>
    </text:p>
  </style:footer>
</style:master-page>
```

Use a separate master page for a different header/footer or orientation. The
example declares a `Standard` master for the initial A4 layout, plus `Portrait`
and `Landscape` masters for later section changes. Selecting a custom master
on the first paragraph can export a leading page break, so use the default
`Standard` master at the document start.

### Start a new page or change orientation

Inside `office:styles`:

```xml
<style:style style:name="LandscapePage" style:family="paragraph"
             style:master-page-name="Landscape">
  <style:paragraph-properties fo:break-before="page"
                              fo:keep-with-next="always"/>
  <style:text-properties fo:font-size="19pt" fo:font-weight="bold"/>
</style:style>
```

Use that paragraph style on the first heading of the new section:

```xml
<text:h text:outline-level="1" text:style-name="LandscapePage">
  Product portfolio and regional mix
</text:h>
<ra:table name="products" .../>
```

`NextPage` in the example requests a new portrait page. Reapply it after a
landscape section to switch back. To insert a break without changing the page
style, use a paragraph style with `fo:break-before="page"` and omit the master-page
selection. Do not rely on empty paragraphs to push content onto a new page.

### Place dynamic content in document flow

```xml
<text:h text:outline-level="1" text:style-name="Heading">
  Regional performance
</text:h>
<ra:paragraphs name="financial_commentary" style-name="Body"/>
<ra:table name="financial"
    table-style-name="ReportTable"
    column-style-names="Wide Num Num Num Num"
    header-cell-style-name="Header"
    body-cell-style-name="Cell"
    alternate-cell-style-name="Alternate"
    header-paragraph-style-name="HeaderText"
    body-paragraph-style-name="TableText"/>
<text:p>
  <ra:image name="trend" width="17.2cm" height="6.1cm"/>
</text:p>
```

A table becomes a native editable Word table. The generated header is repeated
when the table continues to another page. `cohorts` demonstrates 64 records
spanning multiple pages. Column widths come from the named table-column styles and
must fit the current page's usable width. Wider data should use an explicitly
landscape section, as the product page does.

`ra:paragraphs` belongs directly in `office:text`. It turns blank lines into
paragraphs. `ra:text` belongs within `text:p`, `text:h` or `text:span` and supplies
inline text. An image slot in Writer belongs in a paragraph and remains anchored
in the text flow. Exact pagination may change with fonts, content or Office
versions. A forced section break establishes a starting page, not a guarantee
that every section fits on exactly one page.

## PPTX slides

Impress defines one slide with one `draw:page` directly inside
`office:presentation`. XML order is slide order. A slide name is a useful authoring
label; changing it does not rename input slots.

### Define the slide canvas and master

Inside `office:automatic-styles`:

```xml
<style:page-layout style:name="SlideLayout">
  <style:page-layout-properties fo:page-width="33.867cm"
      fo:page-height="19.05cm" style:print-orientation="landscape"/>
</style:page-layout>
```

Inside `office:master-styles`:

```xml
<style:master-page style:name="Standard"
                   style:page-layout-name="SlideLayout"/>
```

These dimensions establish a 16:9 deck. The canvas does not have Writer-style
flowing page margins. Frame coordinates define the safe area. The comprehensive
example uses approximately `1.8cm` left/right margins.

### Define a complete slide

```xml
<draw:page draw:name="03 Regional performance"
           draw:master-page-name="Standard">
  <draw:frame draw:name="title-3" draw:style-name="Frame"
      svg:x="1.8cm" svg:y="1.1cm" svg:width="30cm" svg:height="2cm">
    <draw:text-box>
      <text:p text:style-name="SlideTitle">Every region grew from Q2</text:p>
    </draw:text-box>
  </draw:frame>
  <draw:frame draw:name="financial-frame"
      svg:x="1.8cm" svg:y="4cm" svg:width="29.8cm" svg:height="7cm">
    <ra:table name="financial" .../>
  </draw:frame>
  <draw:frame draw:name="commentary" draw:style-name="Frame"
      svg:x="1.8cm" svg:y="12cm" svg:width="29.8cm" svg:height="4cm">
    <draw:text-box>
      <text:p text:style-name="Body">
        <ra:text name="financial_commentary"/>
      </text:p>
    </draw:text-box>
  </draw:frame>
</draw:page>
```

Coordinates are measured from the top-left corner of the slide. `x`/`y` select
position; width/height select the available area. Use unique frame names. Text
frames contain `draw:text-box`; a native table goes directly in its table frame.
Text does not automatically flow to another slide. Resize or restructure the
content when it exceeds the frame. The renderer does not invent extra slides.

For example, define the paragraph style in `office:automatic-styles`:

```xml
<style:style style:name="SlideTitle" style:family="paragraph">
  <style:paragraph-properties fo:margin-bottom="0cm"/>
  <style:text-properties style:font-name="DejaVu Sans"
      fo:font-size="30pt" fo:font-weight="bold" fo:color="#18343D"/>
</style:style>
```

### Preserve native table colors

Impress requires a table template to preserve the designed header and banded-row
colors. Define this in `office:styles`, along with the referenced `Header`, `Cell`
and `Alternate` table-cell styles:

```xml
<table:table-template table:name="Northstar">
  <table:body table:style-name="Cell"/>
  <table:first-row table:style-name="Header"/>
  <table:odd-rows table:style-name="Alternate"/>
  <table:even-rows table:style-name="Cell"/>
</table:table-template>
```

Select it on the table slot using `table-template-name="Northstar"`. Report Agent
binds the generated table to that template and enables first-row and banded-row
styling. Cell padding and text styles remain explicit. The comprehensive FODP
includes the LibreOffice graphic fill properties needed by its cell styles.
Without the table-template binding, Impress may substitute its default table theme.

### Define static and animated chart slots

Image/animation slots belong directly within `draw:page` and generate their own
positioned image frame:

```xml
<ra:image name="trend" x="2cm" y="7cm" width="29.5cm" height="9.3cm"/>
<ra:animation name="revenue_animation"
    x="2cm" y="4cm" width="29.5cm" height="11cm"
    fit="contain" start="automatic" loop="true"/>
```

The animated slide uses the second slot on its own slide. It receives a GIF built
from a fetched monthly DataFrame. `template.yaml` selects the registered generator
and its table dependency; `render.py` supplies the data-source adapter. Position and
size stay in the FODP source. The final PPTX embeds the GIF rather than referring
to a temporary file. The PNG poster is retained for static previews.

Add a slide by copying a `draw:page`, assigning unique frame names, and updating
its content/slots. Add any new input names to metadata and runtime values. Remove
an unused input declaration when removing its last slot. Reorder slides by moving
whole `draw:page` elements. Existing PPTX template filling is not part of this
workflow.

## XLSX tabs

In a spreadsheet document, each `table:table` directly inside
`office:spreadsheet` defines one sheet/tab. The `table:name` attribute defines its
visible name. XML order determines tab order.

### Define a template-owned tab

```xml
<office:spreadsheet>
  <table:table table:name="Summary" table:style-name="ReportTable">
    <table:table-column table:style-name="Wide"/>
    <table:table-column table:style-name="Wide"/>
    <table:table-row>
      <table:table-cell office:value-type="string">
        <text:p>Q3 revenue ($000)</text:p>
      </table:table-cell>
      <table:table-cell table:formula="of:=SUM([Regions.C2:Regions.C5])"
                        office:value-type="float"/>
    </table:table-row>
  </table:table>
  <ra:table name="financial_raw" sheet-name="Regions" .../>
</office:spreadsheet>
```

A row contains cells in left-to-right order. With no repeats or merged cells, the
first row is Excel row 1 and its first cell is A1. Use a cell with `ra:cell` for a
dynamic literal label, such as the reporting period on Summary. Formulas remain
explicit trusted template content and use ODF formula syntax, with `of` bound to
`urn:oasis:names:tc:opendocument:xmlns:of:1.2`.

The example places Summary first and references later tabs. Report Agent clears
source formula caches before conversion so Calc recalculates against runtime
values, including forward references. The output stores both formulas and the
resulting cached values. Do not supply stale displayed numbers as formula results.
The current tested subset includes SUM, arithmetic and COUNTA.

### Define a complete dynamic data tab

```xml
<ra:table name="financial_raw" sheet-name="Regions"
    table-style-name="ReportTable"
    column-style-names="Wide Num Num Num Num"
    column-cell-style-names="Cell Numeric Numeric Rate Rate"
    header-cell-style-name="Header"
    max-rows="100" max-columns="10"/>
```

This slot creates an entire sheet, with column labels on row 1 and runtime records
beginning on row 2. It does not insert rows into an existing tab or move formulas
around. In this example, `Regions.C2:C5` covers the four individual regions and
excludes the precomputed Total on row 6. Sheet names must be unique. Renaming a
tab also requires updating references to it in formulas.

Numeric data stays numeric. Cell styles control its visible number format.
`Rate` displays source values such as `24.3` with a literal percent suffix. If your
data uses fractional rates such as `0.243`, define an ODF percentage style instead
of reusing that literal-suffix style. Missing renewal values remain blank, not zero.

### Set column widths, number formats and print pages

```xml
<style:style style:name="Wide" style:family="table-column">
  <style:table-column-properties style:column-width="7cm"/>
</style:style>
<number:number-style style:name="Decimal">
  <number:number number:decimal-places="1" number:grouping="true"/>
</number:number-style>
<style:style style:name="Numeric" style:family="table-cell"
             style:data-style-name="Decimal">
  <style:table-cell-properties fo:padding="0.16cm"/>
</style:style>
```

Put these in `office:automatic-styles`, with the `number` namespace declared as
in the complete source. A sheet style can reference a print master page to select
paper size, orientation and scaling. Those are print/PDF settings; they do not
define the sheet's row/column grid or its name. Keep the workbook legible at normal
zoom rather than using print scaling to hide cramped columns.

## Table styling attributes

`ra:table` supports these explicit template references:

| Attribute | Meaning |
| --- | --- |
| `table-style-name` | Table or sheet style |
| `table-template-name` | Named Impress table template for header/banded-row colors |
| `column-style-names` | Space-separated table-column styles, exactly one per column |
| `column-cell-style-names` | Body-cell styles, exactly one per column |
| `alternate-column-cell-style-names` | Per-column styles for alternate body rows |
| `header-cell-style-name` / `body-cell-style-name` | Header/body fallback cell styles |
| `alternate-cell-style-name` | Alternate-row fallback style |
| `header-paragraph-style-name` / `body-paragraph-style-name` | Text style within generated cells |
| `header-row-style-name` / `body-row-style-name` | ODF row styles |

Per-column styles take precedence over fallback cell styles. A paragraph style can
override cell text formatting, so use a white `HeaderText` paragraph style on a
dark header fill. Referenced styles must exist. The number of per-column names
must match the DataFrame's column count; mismatches fail explicitly.

## Review and supported limits

Build after each layout change. Inspect the native package's structure and values,
then render the exported file for visual review. The comprehensive examples include
portrait/landscape sections, table continuation, nine explicit slides, seven tabs,
forward-tab formulas and the original animated media. Source XML that parses is
not evidence that fonts, widths or object positions survived export.

Animations require Slide Show playback checks in a target PowerPoint version;
PDF previews show only a static frame. Desktop app control was not approved in the
current environment, so no native PowerPoint playback claim is made. See the
[Office guide](office-reports.md) for current deployment/format limits and the
[ODF 1.3 schema](https://docs.oasis-open.org/office/OpenDocument/v1.3/os/part3-schema/OpenDocument-v1.3-os-part3-schema.html)
for the complete vocabulary. Writer's
[page style guide](https://help.libreoffice.org/latest/en-GB/text/swriter/guide/pagestyles.html)
explains the relationship between page styles and explicit page breaks.

The comprehensive DOCX uses a `Standard` master bound to `PortraitLayout` as its
initial A4 page. Its first paragraph uses `CoverStart` with `fo:break-before="auto"`
and no master-page reassignment. This avoids exporting a forced break before the
first paragraph, which some viewers show as an empty first page. Keep explicit
master selection and page breaks for later sections. Its footer styles reserve
space between flowing tables and page numbering. The workbook print layout fits one page across
and permits multiple pages down, keeping the long cohort tab readable when printed.
