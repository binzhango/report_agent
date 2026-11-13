"""Measure preparation and private-profile conversion for Office jobs."""

import argparse
import json
from pathlib import Path
from time import perf_counter

import pandas as pd

from report_agent import RenderRequest, TableInput, TextInput, create_renderer

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("runs must be positive")
    directory = ROOT / "output/benchmarks/office"
    directory.mkdir(parents=True, exist_ok=True)
    timings = {}
    for fmt in ("docx", "xlsx"):
        samples = []
        for run in range(args.runs):
            start = perf_counter()
            inputs = {
                "sales": TableInput(
                    pd.DataFrame(
                        {
                            "Region": [f"Region {i}" for i in range(100)],
                            "Revenue": list(range(100)),
                        }
                    )
                )
            }
            if fmt == "docx":
                inputs.update(
                    title=TextInput("Benchmark"),
                    summary=TextInput("Representative report with 100 rows."),
                )
            result = create_renderer().render(
                RenderRequest(
                    ROOT / f"examples/office_{fmt}",
                    ROOT / f"examples/office_{fmt}/template.yaml",
                    inputs,
                    directory / f"sample-{fmt}-{run}.{fmt}",
                )
            )
            if result.output_path is None:
                raise RuntimeError(result.diagnostics)
            samples.append(
                {
                    "seconds": perf_counter() - start,
                    "bytes": result.output_path.stat().st_size,
                }
            )
        timings[fmt] = samples
    output = directory / "timings.json"
    output.write_text(
        json.dumps(
            {
                "experimental": True,
                "scope": (
                    "100-row preparation, conversion, verification, "
                    "publication; no preview"
                ),
                "runs": timings,
            },
            indent=2,
        )
    )
    print(output)


if __name__ == "__main__":
    main()
