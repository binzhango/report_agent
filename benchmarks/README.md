# Report generation benchmark

Run from the repository root with texres on `PATH`:

```sh
uv run python benchmarks/report_generation.py --runs 10
```

The benchmark generates real PDFs using the production renderer. It records one
first request separately, then ten further sequential requests for each case.
Every request prepares its own content and generates a new PDF. Temporary PDFs
and assets are removed after the benchmark; every timing is retained in
`output/benchmarks/report-generation.json`.

## Local measurement: November 9, 2026

This historical baseline predates the November 10 code review and figure-export
cleanup. Rerun the command above to measure the current implementation.

Environment: macOS ARM64, Python 3.12.9, texres 0.7.10, pandas 3.1.1,
matplotlib 3.11.2, Jinja2 3.1.6. CPU model and memory were unavailable to the
benchmark process. Measurements are local observations, not service guarantees.

| Sample | Pages | Median render | Render min-max | Median preparation + render | First request, preparation + render |
| --- | --- | --- | --- | --- | --- |
| Plain text | 1 | 57 ms | 56-72 ms | 57 ms | 60 ms |
| Comprehensive | 7 | 380 ms | 366-382 ms | 430 ms | 506 ms |

The comprehensive case includes a logo, a live matplotlib figure, an existing
graph PDF, six tables including two heatmaps, grouped rows, and a 64-row
multi-page appendix. All 22 builds succeeded without compiler warnings.

## Timing boundaries

- **Preparation:** create runtime values and regenerate upstream assets. For the
  comprehensive report this includes DataFrames, the logo PNG, graph objects,
  and the pre-rendered graph PDF.
- **Render:** create the renderer, load metadata/templates, validate inputs,
  stage assets, export the live figure, render native tables and the complete
  template, run texres, publish the PDF/source/assets/logs, and clean the workspace.
- **Total:** elapsed time for preparation and render in that request. Median
  total is computed from total samples, not by adding component medians.
- **Excluded:** Python process startup/imports, database retrieval, model calls,
  PDF page-count inspection, and writing benchmark results.

texres gets a fresh workspace and private cache on every request, matching the
current renderer. OS and font caches are already warm. The separately recorded
first request is the first timed request in this process, not a measurement after
reboot or a pristine font-cache build.

Runs are sequential in one process. These results do not establish concurrent
throughput, memory limits, latency under contention, or behavior for much larger
tables/documents. Ten samples characterize a small local run; tail-latency
percentiles would need a larger sample.
