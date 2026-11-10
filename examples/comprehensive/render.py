"""Build an illustrative business report exercising every implemented input type."""

# Configure writable graphics caches before importing plotting libraries.
# ruff: noqa: E402

import os
from pathlib import Path

# Keep font caches with generated artifacts when running this standalone example.
BUNDLE = Path(__file__).resolve().parent
ROOT = BUNDLE.parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "output/matplotlib-cache"))
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / "output/cache"))

import matplotlib as mpl
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
from PIL import Image, ImageDraw, ImageFont

from report_agent import (
    FigureInput,
    GraphInput,
    ImageInput,
    RenderRequest,
    TableInput,
    TextInput,
    create_renderer,
)

INK = "#18343D"
TEAL = "#087E8B"
MUTED = "#5A6C73"


def make_logo(destination: Path) -> None:
    image = Image.new("RGB", (760, 150), "white")
    draw = ImageDraw.Draw(image)
    for i, height in enumerate((45, 75, 110)):
        draw.rounded_rectangle(
            (10 + i * 30, 130 - height, 32 + i * 30, 130), radius=4, fill=TEAL
        )
    font_file = Path(mpl.get_data_path()) / "fonts/ttf/DejaVuSans-Bold.ttf"
    draw.text(
        (125, 38), "NORTHSTAR", font=ImageFont.truetype(str(font_file), 65), fill=INK
    )
    image.save(destination)


def style_axis(axis) -> None:
    axis.set_axisbelow(True)
    axis.grid(axis="y", color="#E3EBEC", linewidth=0.8)
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.spines["bottom"].set_color("#CCD8DB")
    axis.tick_params(axis="both", length=0, labelcolor=MUTED, pad=8)


def build_inputs(asset_root: Path) -> dict:
    asset_root.mkdir(parents=True, exist_ok=True)
    logo = asset_root / "northstar.png"
    make_logo(logo)
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"]
    revenue = np.array([1.12, 1.18, 1.25, 1.30, 1.39, 1.44, 1.50, 1.58, 1.69])
    plan = np.array([1.10, 1.15, 1.22, 1.28, 1.34, 1.40, 1.46, 1.51, 1.58])
    q2, q3 = revenue[3:6].sum(), revenue[6:9].sum()
    growth = (q3 / q2 - 1) * 100

    trend = Figure(figsize=(8.3, 2.65), layout="constrained")
    axis = trend.subplots()
    style_axis(axis)
    axis.fill_between(range(9), revenue, 1.0, color=TEAL, alpha=0.07)
    axis.plot(
        months,
        revenue,
        color=TEAL,
        marker="o",
        linewidth=2.5,
        markersize=5,
        label="Actual",
    )
    axis.plot(
        months, plan, color="#99ABB2", linewidth=1.7, linestyle="--", label="Plan"
    )
    axis.set_ylim(1.0, 1.85)
    axis.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"${value:.1f}m"))
    axis.legend(loc="upper left", frameon=False, ncol=2)
    axis.annotate(
        "$1.69m",
        (8, 1.69),
        xytext=(-24, 14),
        textcoords="offset points",
        color=TEAL,
        weight="bold",
    )

    regions = ["North America", "EMEA", "APAC", "Latin America"]
    q3_region = np.array([1980.0, 1320.0, 930.0, 540.0])
    q2_region = np.array([1700.0, 1170.0, 800.0, 460.0])
    margins = np.array([27.0, 22.0, 23.5, 21.0])
    margin = float(np.average(margins, weights=q3_region))
    financial = pd.DataFrame(
        {
            "Region": regions,
            "Q2 revenue": q2_region,
            "Q3 revenue": q3_region,
            "Growth %": (q3_region / q2_region - 1) * 100,
            "Margin %": margins,
        }
    )
    financial.loc[len(financial)] = [
        "Total",
        q2_region.sum(),
        q3_region.sum(),
        growth,
        margin,
    ]
    comparison = pd.DataFrame(
        {
            "Channel": ["Direct", "Partner", "Self-service"],
            "Revenue ($000)": [2630.0, 1390.0, 750.0],
            "New accounts": [145, 92, 140],
            "Retention %": [96.3, 94.7, 91.4],
        }
    )
    sequential = pd.DataFrame(
        [[94, 96, 97, 98], [88, 90, 92, 93], [91, 93, 95, 96], [86, 89, 92, 94]],
        index=regions,
        columns=["Jun", "Jul", "Aug", "Sep"],
    )
    labels = ["Retention", "Satisfaction", "Response time", "Adoption"]
    diverging = pd.DataFrame(
        [
            [1.0, 0.78, -0.64, 0.56],
            [0.78, 1.0, -0.72, 0.61],
            [-0.64, -0.72, 1.0, -0.43],
            [0.56, 0.61, -0.43, 1.0],
        ],
        index=labels,
        columns=labels,
    )
    regional = Figure(figsize=(8.3, 3.25), layout="constrained")
    axis = regional.subplots()
    style_axis(axis)
    axis.grid(False)
    axis.barh(
        regions[::-1],
        q3_region[::-1] / 1000,
        color=["#C7DFE2", "#8FBBC2", "#4D9CA7", TEAL],
        height=0.55,
    )
    axis.set_xlim(0, 2.35)
    axis.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"${value:.1f}m"))
    for i, amount in enumerate(q3_region[::-1]):
        axis.text(
            amount / 1000 + 0.04,
            i,
            f"${amount / 1000:.2f}m",
            va="center",
            color=INK,
            fontsize=10,
        )
    graph_file = asset_root / "regional-revenue.pdf"
    regional.savefig(
        graph_file, format="pdf", metadata={"CreationDate": None, "ModDate": None}
    )

    products = pd.DataFrame(
        [
            [1740, 95.8],
            [1240, 96.7],
            [740, 94.1],
            [510, 93.5],
            [320, 92.6],
            [220, np.nan],
        ],
        index=pd.MultiIndex.from_tuples(
            [
                ("Platform", "Core"),
                ("Platform", "Enterprise"),
                ("Solutions", "Analytics"),
                ("Solutions", "R&D Services"),
                ("New offers", "Café Insights"),
                ("New offers", "Workflow Plus"),
            ]
        ),
        columns=["Revenue ($000)", "Renewal %"],
    )
    rng = np.random.default_rng(42)
    cohorts = pd.DataFrame(
        {
            "Cohort": [f"C-{i:03}" for i in range(1, 65)],
            "Region": [regions[i % 4] for i in range(64)],
            "Accounts": rng.integers(18, 72, 64),
            "ARR ($000)": rng.integers(240, 1600, 64),
            "Retention %": rng.integers(88, 99, 64),
        }
    )
    return {
        "logo": ImageInput(logo),
        "period": TextInput("July - September 2026"),
        "title": TextInput("Momentum with discipline"),
        "summary": TextInput(
            f"Northstar closed the quarter with ${q3:.2f} million in revenue, "
            f"up {growth:.1f}% "
            "from Q2. Growth was broad-based across regions, supported by expansion "
            "in the platform business and a steady improvement in service attainment."
        ),
        "revenue": TextInput(f"${q3:.2f}m"),
        "growth": TextInput(f"+{growth:.1f}% quarter on quarter"),
        "margin": TextInput(f"{margin:.1f}%"),
        "retention": TextInput("94.6%"),
        "trend": FigureInput(trend),
        "outlook": TextInput(
            "Management enters Q4 with a balanced regional revenue base. The immediate "
            "priority is to preserve service quality as account coverage expands."
        ),
        "financial": TableInput(financial),
        "comparison": TableInput(comparison),
        "financial_commentary": TextInput(
            f"North America contributed {q3_region[0] / q3_region.sum():.1%} "
            "of revenue. "
            f"The blended operating margin was {margin:.1f}%. Partner-led acquisition "
            "continues to complement direct sales, while self-service provides a "
            "lower-touch route for smaller customers."
        ),
        "sequential": TableInput(sequential),
        "diverging": TableInput(diverging),
        "regional_graph": GraphInput(graph_file),
        # assumptions uses its metadata default; optional_note is deliberately omitted.
        "products": TableInput(products),
        "disclaimer": TextInput(
            "This report uses synthetic, illustrative data. It does not describe an "
            "actual company or provide an investment recommendation."
        ),
        "cohorts": TableInput(cohorts),
    }


def main() -> None:
    with mpl.rc_context(
        {"font.family": "DejaVu Sans", "font.size": 10, "pdf.fonttype": 42}
    ):
        inputs = build_inputs(ROOT / "output/sample-assets/comprehensive")
        result = create_renderer().render(
            RenderRequest(
                template=BUNDLE,
                metadata=BUNDLE / "template.json",
                inputs=inputs,
                output=ROOT / "output/pdf/comprehensive-report.pdf",
            )
        )
    for diagnostic in result.diagnostics:
        print(
            f"{diagnostic.severity}: {diagnostic.input_name or diagnostic.stage}: "
            f"{diagnostic.message}"
        )
    if result.pdf_path is None:
        raise SystemExit(1)
    print(result.pdf_path)


if __name__ == "__main__":
    main()
