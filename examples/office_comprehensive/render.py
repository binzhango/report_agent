"""Build comprehensive Office examples through Report Agent's own backend."""

# ruff: noqa: E402
import argparse
import os
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent
ROOT = BUNDLE.parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "output/matplotlib-cache"))
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / "output/cache"))

import matplotlib as mpl
from data import ExampleDataSource, build_inputs, revenue_animation

from report_agent import RenderRequest, TextInput, create_renderer
from report_agent.metadata.loader import MetadataLoader
from report_agent.resolution.animations import AnimationGenerators
from report_agent.resolution.models import QuerySource
from report_agent.resolution.resolver import ContentResolver


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=["docx", "pptx", "xlsx"])
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "output/office_comprehensive"
    )
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    with mpl.rc_context({"font.family": "DejaVu Sans", "font.size": 10}):
        values, raw = build_inputs(args.output_root / "assets")
        for fmt in [args.only] if args.only else ["docx", "pptx", "xlsx"]:
            metadata = MetadataLoader().load(BUNDLE / fmt / "template.yaml")
            source = {**values, **raw, "period": TextInput("July to September 2026")}
            inputs = {
                name: value for name, value in source.items() if name in metadata.inputs
            }
            resolver = None
            queries = {}
            if fmt == "pptx":
                resolver = ContentResolver(
                    sources={"example": ExampleDataSource()},
                    animation_generators=AnimationGenerators(
                        {"revenue_over_time": revenue_animation}
                    ),
                )
                queries = {
                    "animation_data": QuerySource(
                        connection="example",
                        query="monthly_revenue",
                        row_limit=100,
                    )
                }
            label = {
                "docx": "document",
                "pptx": "presentation",
                "xlsx": "workbook",
            }[fmt]
            output = args.output_root / f"comprehensive-{label}.{fmt}"
            result = create_renderer(resolver=resolver).render(
                RenderRequest(BUNDLE / fmt, metadata, inputs, output, queries=queries)
            )
            if result.output_path is None:
                raise RuntimeError(result.diagnostics)
            print(result.output_path)


if __name__ == "__main__":
    main()
