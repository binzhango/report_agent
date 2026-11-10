"""Demonstrate JSON/YAML presentation settings keyed by placeholder name."""

from pathlib import Path

import pandas as pd
from matplotlib.figure import Figure
from PIL import Image, ImageDraw

from report_agent import (
    FigureInput,
    ImageInput,
    RenderRequest,
    TableInput,
    TextInput,
    create_renderer,
)


def main() -> None:
    bundle = Path(__file__).resolve().parent
    root = bundle.parents[1]
    assets = root / "output/sample-assets/placeholder-styles"
    assets.mkdir(parents=True, exist_ok=True)
    logo = Image.new("RGB", (120, 120), "#087E8B")
    draw = ImageDraw.Draw(logo)
    for index, height in enumerate([30, 50, 70]):
        draw.rectangle(
            (22 + index * 28, 95 - height, 40 + index * 28, 95), fill="white"
        )
    logo_path = assets / "logo.png"
    logo.save(logo_path)
    trend = Figure(figsize=(6, 2.6), layout="constrained")
    axis = trend.subplots()
    axis.plot(["Jul", "Aug", "Sep"], [1.5, 1.58, 1.69], marker="o", color="#087E8B")
    axis.set_ylabel("Revenue (USD millions)")
    axis.spines[["top", "right"]].set_visible(False)
    financial = pd.DataFrame(
        {
            "Region": ["North America", "EMEA", "APAC"],
            "Revenue ($000)": [1980.0, 1320.0, 930.0],
            "Margin %": [27.0, 22.0, 23.5],
        }
    )
    result = create_renderer().render(
        RenderRequest(
            template=bundle,
            metadata=bundle / "template.json",
            inputs={
                "title": TextInput("Styles attached to placeholder names"),
                "summary": TextInput(
                    "The summary is plain content. Its font, color, spacing, heading, "
                    "and shaded container come from the summary configuration "
                    "in JSON.\n\n"
                    "The template still contains only the summary placeholder followed "
                    "by a paragraph break. Images, graphs, and tables use "
                    "this same mechanism."
                ),
                "logo": ImageInput(logo_path),
                "trend": FigureInput(trend),
                "financial": TableInput(financial),
            },
            output=root / "output/pdf/placeholder-styles.pdf",
        )
    )
    for diagnostic in result.diagnostics:
        print(f"{diagnostic.severity}: {diagnostic.message}")
    if result.pdf_path is None:
        raise SystemExit(1)
    print(result.pdf_path)


if __name__ == "__main__":
    main()
