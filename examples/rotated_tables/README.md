# Rotated table example

```sh
uv run python examples/rotated_tables/render.py
```

Output: `output/pdf/rotated-tables.pdf`. The same native DataFrame table appears
twice, using one runtime input and two occurrences of its template placeholder.

| Page | Template environment | Result |
| --- | --- | --- |
| 1 | `landscape` from `pdflscape` | PDF page has a 90-degree rotation attribute; viewers display it horizontally |
| 2 | `sidewaystable` from `rotating` | Page remains portrait; the table and surrounding block rotate 90 degrees |

The table adapter produces a normal `tabular` fragment. Rotation is controlled
by the complete `.tex` template; no new runtime input type or metadata field is
needed. This demonstrates explicit template layout, not automatic orientation
selection by the renderer.

For wide tables that also span multiple pages, use `longtable` inside a landscape
environment. A `sidewaystable` is a single-page float and cannot paginate a long
table. Headers and page-number placement in landscape sections require template
styling if they should follow the rotated text rather than the portrait page.

See [pdflscape](https://ctan.org/pkg/pdflscape) and
[rotating](https://ctan.org/pkg/rotating) for the package behavior.
