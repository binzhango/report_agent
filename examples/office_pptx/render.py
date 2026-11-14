"""Fetch example data, generate a finite animation, and build an embedded PPTX."""

from pathlib import Path

import pandas as pd
from matplotlib.animation import FuncAnimation
from matplotlib.figure import Figure

from report_agent import RenderRequest, create_renderer
from report_agent.metadata.loader import MetadataLoader
from report_agent.resolution.animations import AnimationGenerators
from report_agent.resolution.models import QuerySource
from report_agent.resolution.resolver import ContentResolver

ROOT = Path(__file__).resolve().parent


class DemoDataSource:
    """Replace with the application's bounded read-only database adapter."""

    def fetch(self, source):
        return pd.DataFrame(
            {"period": range(12), "sales": [3, 6, 4, 8, 11, 9, 13, 15, 14, 19, 21, 23]}
        )


def sales_over_time(tables, options):
    data = tables["sales_data"]
    figure = Figure(figsize=(6, 3))
    axis = figure.subplots()
    axis.set(xlim=(0, 11), ylim=(0, 25), xlabel="Month", ylabel="Sales")
    (line,) = axis.plot([], [], color="#205080", linewidth=3)
    label = axis.text(0.05, 0.9, "", transform=axis.transAxes)

    def update(frame):
        line.set_data(data.period[: frame + 1], data.sales[: frame + 1])
        label.set_text(f"Month {frame + 1}: {data.sales.iloc[frame]}")
        return line, label

    return FuncAnimation(figure, update, frames=12, interval=250, repeat=True)


def create_resolver():
    """Application-owned adapter wiring, also usable as a CLI resolver factory."""
    return ContentResolver(
        sources={"demo": DemoDataSource()},
        animation_generators=AnimationGenerators({"sales_over_time": sales_over_time}),
    )


def main():
    metadata = MetadataLoader().load(ROOT / "template.yaml")
    result = create_renderer(resolver=create_resolver()).render(
        RenderRequest(
            ROOT,
            metadata,
            {},
            Path("output/office/animated-sales.pptx"),
            queries={
                "sales_data": QuerySource(
                    connection="demo", query="demo sales", row_limit=100
                )
            },
        )
    )
    if result.output_path is None:
        raise RuntimeError(result.diagnostics)
    print(result.output_path)


if __name__ == "__main__":
    main()
