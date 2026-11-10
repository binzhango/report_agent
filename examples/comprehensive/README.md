# Comprehensive report example

For a page-by-page explanation with screenshots, source mappings, metadata,
rendering objects, and artifact inspection, read the
[detailed walkthrough](../../docs/comprehensive-example-walkthrough.md).

```sh
uv run python examples/comprehensive/render.py
```

Output: `output/pdf/comprehensive-report.pdf`, with retained TeX, graphics,
and compiler log in `output/pdf/comprehensive-report.artifacts/`.

The seven-page report uses synthetic business data. All report content flows
through the public `ReportRenderer` API and its actual content adapters.

| Report element | Project capability |
| --- | --- |
| Company logo | PNG passed as `ImageInput`; JPEG and PDF assets also supported |
| Executive summary and KPI values | Escaped `TextInput` strings, including currency, percentages, and ampersands |
| Revenue trend | Live matplotlib `Figure` passed as `FigureInput` |
| Regional revenue bars | Existing vector PDF passed as `GraphInput` |
| Regional financial summary | Native DataFrame table with financial preset, precision, thousands separators, hidden index |
| Channel comparison | Comparison preset highlights column maxima |
| Service attainment | Sequential heatmap with a table-wide color scale |
| Correlation matrix | Diverging heatmap with a fixed -1 to +1 scale |
| Product detail | MultiIndex row groups, accented text, missing-value display |
| Customer cohort appendix | Multi-page native `longtable`, repeating headers, continuation footer |
| Planning assumptions | Text default supplied by template metadata |
| Optional note | Omitted optional input renders empty |
| Headings, KPI boxes, captions, numbered list, headers/footers | Layout and static content owned by the complete `.tex` template |

`template.json` and `template.yaml` contain equivalent metadata. Change the
selected metadata path in `render.py` to use YAML. Python mappings and validated
metadata models work through the same API.

Graphics metadata accepts a positive dimension such as `38mm`, `3in`, or
`0.9\linewidth`. Tables accept `preset`, `precision` (0-8), `show_index`, and
`longtable`. Templates must load the packages needed by their content, such as
`graphicx`, `booktabs`, `multirow`, `longtable`, and `xcolor` with the table option.
Wide-table resizing, landscape policies, arbitrary chart definitions, and the
Great Tables backend remain future work.
