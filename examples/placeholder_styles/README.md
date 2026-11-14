# LaTeX placeholder styles example

This schema-v1 PDF example uses `LatexPdfBackend` and `LatexPlaceholderStyler`.
Office templates use [ODF styles](../../docs/office-template-authoring.md) instead.

```sh
uv run python examples/placeholder_styles/render.py
```

Generates `output/pdf/placeholder-styles.pdf`: a three-page demonstration of
per-placeholder typography, section headings, layout, and containers for text,
images, graphs, and tables. The template keeps ordinary keys such as
`<<summary>>\par`; styles live under `inputs.summary.style` in JSON/YAML.

See the [style guide](../../docs/placeholder-styles.md) for the lookup flow,
class responsibilities, configuration reference, and inline/block limitations.

`template.json` and `template.yaml` are equivalent. Select the YAML path in
`render.py` to use it. The template loads `xcolor`, `graphicx`, `booktabs`, and
`multirow` as required by the content and presentation layers.
