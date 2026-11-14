# LaTeX placeholder style configuration

This guide applies to schema-v1 PDF templates and `LatexPdfBackend`. Schema-v2
Office templates define styles in Flat ODF; see the
[Office authoring reference](office-template-authoring.md). They do not use
`inputs.<name>.style` or `LatexPlaceholderStyler`.

Each placeholder name identifies both its content declaration and its presentation
settings. The template does not need a separate style expression:

```tex
<<summary>>\par
```

The engine finds `inputs.summary` in JSON/YAML, renders the supplied value, applies
`inputs.summary.style`, and binds the resulting fragment to `summary`. This works
for text, images, existing graphs, live figures, and native tables.

## A complete configuration example

```json
{
  "id": "styled_report",
  "entrypoint": "main.tex",
  "inputs": {
    "summary": {
      "type": "text",
      "style": {
        "typography": {
          "font_size_pt": 12,
          "line_height_pt": 17,
          "paragraph_spacing_pt": 8,
          "color": "#18343D"
        },
        "layout": {
          "display": "block",
          "alignment": "left",
          "space_before_pt": 12,
          "space_after_pt": 12,
          "heading": {
            "text": "Executive summary",
            "level": "subsection"
          }
        },
        "container": {
          "width": "1\\linewidth",
          "background_color": "#EDF4F4",
          "border_color": "#087E8B",
          "border_width_pt": 0.8,
          "padding_pt": 14
        }
      }
    }
  }
}
```

The caller still passes only content:

```python
inputs = {"summary": TextInput("Revenue grew by 12% during the quarter.")}
```

YAML uses the same models and field names. See the equivalent JSON/YAML files
in [the runnable example](../examples/placeholder_styles/).

## How the objects collaborate

```text
<<summary>> in the template
       |
       +--> inputs.summary.type selects TextRenderer
       |       |
       |       +--> TextInput becomes escaped content
       |
       +--> inputs.summary.style selects presentation options
               |
               +--> LatexPlaceholderStyler wraps the escaped content
                           |
                           +--> Jinja inserts the prepared fragment at <<summary>>
```

The same shared path applies after `ImageRenderer`, `GraphRenderer`, and
`StylerTableRenderer`. None of those adapters needs to duplicate box, heading,
spacing, or page-break code.

| Object | Responsibility |
| --- | --- |
| [PlaceholderStyle](../src/report_agent/metadata/styles.py) | Validate common typography, layout, and container metadata |
| [InputDefinition](../src/report_agent/metadata/models.py) | Attach that style to one input name and reject incompatible longtable containers |
| Content renderer | Convert the typed value into trusted `RenderedContent` |
| [PlaceholderStyler protocol / LatexPlaceholderStyler](../src/report_agent/presentation/styler.py) | Apply scoped presentation to prepared content; preserve its assets and package requirements |
| [ReportRenderer](../src/report_agent/application/service.py) | Load metadata, resolve query/agent content when needed, and select the document backend |
| [LatexPdfBackend](../src/report_agent/backends/latex_pdf.py) | Resolve defaults/optional values, invoke the content strategy, apply presentation, and expand the TeX template |
| [JinjaTemplateEngine](../src/report_agent/templates/engine.py) | Bind the final fragment to the unchanged placeholder name |

The styler does not escape the content again. Text and table adapters already
own content escaping; headings supplied in configuration are escaped separately.
Colors, dimensions, numerical sizes, heading levels, and alignment values are
validated before commands are generated. Arbitrary LaTeX is not a style option.

## Inline and block scopes

### Inline

`style.layout.display` defaults to `inline`. It is suitable for a title inside
a template macro or a phrase inside a paragraph:

```json
{
  "type": "text",
  "style": {
    "typography": {"bold": true, "color": "#087E8B"}
  }
}
```

Only the inserted content is grouped and styled. It does not introduce a paragraph,
heading, box, or page break. The surrounding template remains in control of those
boundaries. Inline font-size changes affect the text run; paragraph leading is
controlled by the containing paragraph.

### Block

Use `display: block` for standalone placeholders such as `<<summary>>\par`.
A block can create a section heading, align its content, add vertical spacing,
start a new page, and optionally wrap its contents in a box.

The generated block begins and ends its own paragraph within a scoped group.
The template's following `\par` may remain. Styles are restored before later
template content is processed.

Place block placeholders at document-flow boundaries. Do not put a block-configured
placeholder inside a title argument, table cell, or another inline-only context.
The engine validates the metadata combination, but does not infer every enclosing
LaTeX context from template source.

## Supported settings

| Group | Fields | Meaning |
| --- | --- | --- |
| `typography` | `font_size_pt` | Font size for rendered text and native table text; inherited by generated headings subject to their LaTeX heading commands |
| `typography` | `line_height_pt` | Paragraph leading; requires font size and block display |
| `typography` | `paragraph_spacing_pt` | Space between paragraphs in the content; requires block display |
| `typography` | `color` | Six-digit `#RRGGBB` text color |
| `typography` | `bold`, `italic` | True enables the font property; false resets it; omission inherits the template |
| `layout` | `display` | `inline` or `block` |
| `layout` | `alignment` | `left`, `center`, or `right`; block only |
| `layout` | `space_before_pt`, `space_after_pt` | Nonnegative space around a block |
| `layout` | `page_break_before`, `page_break_after` | Explicit `\clearpage` before/after the block; flushes pending floats |
| `layout.heading` | `text`, `level`, `numbered` | Plain-text heading; level is section/subsection/subsubsection; unnumbered by default |
| `container` | `width` | Total box width, including border/padding; e.g. `0.9\linewidth` or `100mm` |
| `container` | `padding_pt` | Inner padding; default 8 pt |
| `container` | `background_color`, `border_color` | Six-digit colors; both default to white |
| `container` | `border_width_pt` | Border thickness; default zero |

Container settings require block display. The implementation uses a minipage
inside `\fcolorbox`, deducting padding and border from the requested outer width.
The block alignment positions the box and is also applied inside it. A container
whose padding/border leaves no usable width raises a compiler error.

Typography changes do not recolor image pixels or rewrite the fonts/lines inside
a graph PDF. They affect surrounding text, generated headings, and native table
text. Plot appearance remains with the figure/pre-rendered asset. Table-specific
cell formatting and heatmap rules remain in table metadata such as `preset`.

## Pagination and container limits

- Blocks without a container remain in normal, breakable document flow.
- A box is unbreakable. Its content must fit on one page and within its chosen
  width; the styler does not automatically resize or paginate oversized boxes.
- `longtable: true` can use block styling without a box. Metadata rejects placing
  it inside this unbreakable container, or giving it inline styling.
- Empty content produces no style wrapper, heading, spacing, or page break.
  Surrounding headings and page breaks authored directly in the template remain.
- With no style (or an empty style object), the prepared content receives no
  additional presentation wrapper.

The template must load `xcolor` when using colors/boxes. It must also load the
packages required by its content adapters. Colored table cells require `colortbl`,
supplied explicitly or via `\usepackage[table]{xcolor}`. Before compilation,
fragment requirements
are checked against literal package declarations and `provided_packages` metadata.
They are not automatically injected into the preamble. See the
[package declaration contract](review-hardening.md#package-declarations) for scanner limits.

Automatic column splitting, table-width planning and slot-capability negotiation
are not implemented. Common placeholder presentation does not provide those policies.

## Reuse and customization

A style belongs to a placeholder name. If `<<summary>>` appears twice, both
occurrences receive the same prepared fragment and style. Use two distinct keys
when those occurrences should have different presentation.

The optional schema-v1 `style` field works alongside `preset`, `precision`,
graphics `width`, and `longtable` fields. Existing templates and metadata need no
style configuration to keep working. Global themes and named style inheritance
are not implemented for this LaTeX metadata layer. ODF named styles are a separate
Office-template mechanism.

Applications constructing `ReportRenderer` directly supply its PDF `styler`
collaborator, which is passed to `LatexPdfBackend`. `create_renderer()` supplies
`LatexPlaceholderStyler` automatically.

## Working demonstration

```sh
uv run python examples/placeholder_styles/render.py
```

Output after running the example: `output/pdf/placeholder-styles.pdf`.

| PDF page | Demonstration |
| --- | --- |
| 1 | Inline title style; summary heading, typography, paragraph spacing, colored border/background; subsequent template text retains normal style |
| 2 | Centered image container and graph section, with a page break configured on the image placeholder |
| 3 | Table typography/container, metadata heading, and styled default footer text |

All headings, containers, and page transitions in this example are configured
under individual placeholder names; the `.tex` body contains only the placeholders,
paragraph breaks, and one explanatory paragraph.
