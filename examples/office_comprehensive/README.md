# Comprehensive Office examples

These examples adapt the comprehensive PDF report's synthetic Northstar data to
three complete styled Office templates. Run from the repository root:

```sh
uv run python examples/office_comprehensive/render.py
```

Generated files:

- `output/office_comprehensive/comprehensive-document.docx`
- `output/office_comprehensive/comprehensive-presentation.pptx`
- `output/office_comprehensive/comprehensive-workbook.xlsx`

Use `--only docx`, `--only pptx` or `--only xlsx` for an individual output, or set
`--output-root PATH`. Each output uses a distinct artifact directory. The template
files and metadata are committed source; generated output and chart assets stay
under `output/`.

## Document structure

The DOCX example renders eight pages with the current tested fonts and engine:

| Section | Content | Template mechanism |
| --- | --- | --- |
| Executive overview | Logo, title, reporting period, three metrics, summary, revenue chart | Portrait master and styled document flow |
| Regional and channel performance | Two native tables and commentary | `NextPage` paragraph style |
| Service quality | Two-panel chart, service table and correlation table | `NextPage`, native tables, image slot |
| Product portfolio | Product table, missing renewal rate, regional bar chart | `LandscapePage` switches to landscape |
| Cohort appendix | All 64 records, across three pages with repeated headers | Return to Portrait and a flowing native table |
| Outlook and assumptions | Priorities, definitions, illustrative-data note | `NextPage` |

DOCX content flows. The source does not contain eight hard-coded page containers;
it declares section starts, page styles and content. Pagination can change with
different text or fonts.

## Presentation structure

The PPTX contains nine explicitly authored slides. Every slide is a `draw:page`
in `pptx/main.fodp`, in delivery order:

| Slide | Name | Content |
| --- | --- | --- |
| 1 | Cover | Logo, title, period, revenue and growth |
| 2 | Executive overview | Summary and actual-versus-plan chart |
| 3 | Regional performance | Native regional financial table and commentary |
| 4 | Regional mix | Regional bar chart and outlook |
| 5 | Acquisition channels | Native channel table and account commentary |
| 6 | Service quality | Service heatmap and illustrative correlations |
| 7 | Product portfolio | Native product table and missing-value note |
| 8 | Revenue animation | Embedded 36-frame GIF generated from fetched monthly data |
| 9 | Outlook | Priorities and data note |

Slide size is 16:9. Frames specify coordinates and dimensions in centimetres.
Slide 8 fetches nine monthly records through `ExampleDataSource`, calls the
registered `revenue_over_time` Matplotlib generator, and embeds a 4.5-second GIF
at 8 fps. The final PPTX contains the animation bytes; source media files are not
required during playback. The generator and data adapter are demonstration Python
code supplied by the application, while the placement stays in the XML template.

## Workbook structure

The workbook defines seven ordered tabs in `xlsx/main.fods`:

| Tab | Source | Purpose |
| --- | --- | --- |
| Summary | Explicit template-owned `table:table` | Cross-tab formulas, reporting period and assumptions |
| Regions | `financial_raw` table slot | Q2/Q3 revenue, growth and margin, with a Total record |
| Channels | `channels_raw` table slot | Revenue, new accounts and retention |
| Service | `service_raw` table slot | Monthly service attainment by region |
| Products | `products_raw` table slot | Product revenue and renewal rates, including one missing rate |
| Cohorts | `cohorts_raw` table slot | All 64 customer cohort records |
| Monthly | `monthly_raw` table slot | Actual and planned monthly revenue |

The Summary formulas reference later tabs and exclude duplicate Total rows.
Expected results include Q3 revenue 4,770 ($000), Q2 revenue 4,130 ($000), growth
15.496%, 377 new accounts, product revenue 4,770 ($000), and 64 cohorts. The stored
growth value is unrounded; its cell displays one decimal place. Formula caches
are recalculated from runtime values during conversion. Detail values remain
numeric; text is used only where the underlying value is a label or identifier.

## Files and authoring

- `docx/main.fodt`, `pptx/main.fodp`, `xlsx/main.fods`: complete layout, styles and slots.
- Each directory's `template.yaml`: declared input types, limits and generation dependencies.
- `data.py`: shared PDF-source data with explicit Office adaptations. MultiIndex
  product labels become Group/Product columns. Heatmaps are chart images in the
  document/deck; raw service values remain native cells in the workbook.
- `render.py`: resolution, animation generation and calls to Report Agent.

For complete examples of defining a page style, a page break, a slide, a positioned
text/chart frame, a tab, a formula and column/cell styles, read the
[Office template authoring guide](../../docs/office-template-authoring.md).

The rendered DOCX/PPTX and workbook print views are reviewed through LibreOffice
PDF previews. This checks static appearance, not PowerPoint animation playback.
The Office backend remains experimental pending a released LibreOffice baseline
and native target-application checks described in the
[Office report guide](../../docs/office-reports.md).
