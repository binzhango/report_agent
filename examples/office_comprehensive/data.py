"""Reuse the PDF example's synthetic data, adapting only Office presentation."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.animation import FuncAnimation
from matplotlib.figure import Figure

from report_agent import FigureInput, GraphInput, TableInput, TextInput

ROOT = Path(__file__).resolve().parents[2]
INK, TEAL, MUTED = "#18343D", "#087E8B", "#5A6C73"


def load_source(asset_root):
    spec = importlib.util.spec_from_file_location(
        "pdf_comprehensive", ROOT / "examples/comprehensive/render.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    values = module.build_inputs(asset_root)
    return values


def display_table(frame, decimals=1):
    result = frame.copy()
    for column in result.columns:
        if pd.api.types.is_numeric_dtype(result[column]):
            result[column] = result[column].map(
                lambda v: "--" if pd.isna(v) else f"{v:,.{decimals}f}"
            )
    return TableInput(result)


def build_inputs(asset_root):
    values = load_source(asset_root)
    financial = values["financial"].data
    regional = Figure(figsize=(8, 4), layout="constrained")
    axis = regional.subplots()
    axis.barh(financial.Region[:4][::-1], financial["Q3 revenue"][:4][::-1], color=TEAL)
    axis.set_xlabel("Q3 revenue ($000)")
    axis.spines[["top", "right"]].set_visible(False)
    png = asset_root / "regional-revenue.png"
    regional.savefig(png, dpi=160)
    values["regional_graph"] = GraphInput(png)
    products = values["products"].data.reset_index()
    products.columns = ["Group", "Product", "Revenue ($000)", "Renewal %"]
    sequential = values["sequential"].data.rename_axis("Region").reset_index()
    diverging = values["diverging"].data.rename_axis("Metric").reset_index()
    raw_financial = financial.copy()
    raw_comparison = values["comparison"].data.copy()
    raw_cohorts = values["cohorts"].data.copy()
    values.update(
        financial=display_table(financial),
        comparison=display_table(raw_comparison),
        products=display_table(products),
        sequential=display_table(sequential, 0),
        diverging=display_table(diverging, 2),
    )
    values["cohorts"] = TableInput(raw_cohorts)
    values["title"] = TextInput("Northstar quarterly business review")
    values["report_purpose"] = TextInput(
        "Quarterly operating results for the leadership team. Revenue reached "
        "$4.77 million, up 15.5% from Q2. This review covers regional "
        "performance, acquisition channels, service quality and the customer "
        "cohort appendix."
    )
    values["assumptions"] = TextInput(
        "Revenue is reported in thousands of US dollars unless shown as "
        "millions. Growth compares Q3 with Q2. Margin is weighted by regional "
        "revenue. Service attainment is the share of requests meeting the "
        "target. Correlations are illustrative and do not establish causation."
    )
    values["next_steps"] = TextInput(
        "Preserve service quality as account coverage expands.\n\nReview renewal "
        "coverage for the new product offers. Workflow Plus has no renewal "
        "estimate yet.\n\nTrack partner acquisition alongside direct sales in the"
        " next quarterly review."
    )
    values["cohort_note"] = TextInput(
        "The appendix contains all 64 illustrative customer cohorts. ARR is an "
        "annualized cohort measure and should not be added to quarterly "
        "revenue."
    )
    values["channels_note"] = TextInput(
        "Direct sales generated $2.63 million, partners $1.39 million and self-"
        "service $0.75 million. New accounts totalled 377 across the three "
        "channels."
    )
    heatmap = Figure(figsize=(10, 4), layout="constrained")
    axes = heatmap.subplots(1, 2)
    for ax, frame, title, cmap, low, high, fmt in [
        (
            axes[0],
            values["sequential"].data.set_index("Region").astype(float),
            "Service attainment (%)",
            "YlGnBu",
            80,
            100,
            ".0f",
        ),
        (
            axes[1],
            diverging.set_index("Metric").astype(float),
            "Illustrative correlations",
            "RdBu",
            -1,
            1,
            ".2f",
        ),
    ]:
        ax.imshow(frame, cmap=cmap, vmin=low, vmax=high, aspect="auto")
        ax.set_xticks(range(len(frame.columns)), frame.columns, rotation=25, ha="right")
        ax.set_yticks(range(len(frame.index)), frame.index)
        ax.set_title(title, color=INK, pad=12)
        for (i, j), v in np.ndenumerate(frame.to_numpy()):
            ax.text(
                j,
                i,
                format(v, fmt),
                ha="center",
                va="center",
                color="white" if (v > 96 if low == 80 else abs(v) > 0.65) else INK,
                fontsize=9,
            )
    values["service_chart"] = FigureInput(heatmap)
    monthly = pd.DataFrame(
        {
            "Month": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"],
            "Actual ($m)": [1.12, 1.18, 1.25, 1.30, 1.39, 1.44, 1.50, 1.58, 1.69],
            "Plan ($m)": [1.10, 1.15, 1.22, 1.28, 1.34, 1.40, 1.46, 1.51, 1.58],
        }
    )
    raw = {
        "financial_raw": raw_financial,
        "channels_raw": raw_comparison,
        "service_raw": sequential.astype(
            {c: int for c in sequential.columns if c != "Region"}
        ),
        "products_raw": products,
        "cohorts_raw": raw_cohorts,
        "monthly_raw": monthly,
    }
    return values, {
        name: TableInput(frame.astype(object).where(pd.notna(frame), None))
        for name, frame in raw.items()
    }


class ExampleDataSource:
    def fetch(self, source):
        return pd.DataFrame(
            {
                "month": range(9),
                "actual": [1.12, 1.18, 1.25, 1.30, 1.39, 1.44, 1.50, 1.58, 1.69],
                "plan": [1.10, 1.15, 1.22, 1.28, 1.34, 1.40, 1.46, 1.51, 1.58],
            }
        )


def revenue_animation(tables, options):
    data = tables["animation_data"]
    figure = Figure(figsize=(9, 3.5), layout="constrained")
    ax = figure.subplots()
    ax.set(xlim=(-0.2, 8.2), ylim=(1, 1.85), ylabel="Monthly revenue ($m)")
    ax.set_xticks(
        range(9), ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep"]
    )
    ax.plot(data.month, data.plan, color="#99ABB2", linestyle="--", label="Plan")
    (line,) = ax.plot([], [], color=TEAL, linewidth=3, marker="o", label="Actual")
    label = ax.text(0.02, 0.9, "", transform=ax.transAxes, color=INK)
    ax.legend(loc="upper left", bbox_to_anchor=(0.6, 1), frameon=False, ncol=2)
    ax.spines[["top", "right"]].set_visible(False)

    def update(frame):
        position = frame / 35 * 8
        end = int(position)
        x = list(range(end + 1))
        y = list(data.actual[: end + 1])
        current = float(np.interp(position, data.month, data.actual))
        if end < 8:
            x.append(position)
            y.append(current)
        line.set_data(x, y)
        label.set_text(f"Monthly revenue: ${current:.2f}m")
        return line, label

    return FuncAnimation(figure, update, frames=36, interval=125, repeat=True)
