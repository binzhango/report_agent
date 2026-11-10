"""Content conversion, source ownership, and metadata safety contracts."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from matplotlib.figure import Figure
from PIL import Image
from pydantic import ValidationError

from report_agent.metadata.models import InputDefinition
from report_agent.models.inputs import FigureInput, GraphInput, ImageInput, TableInput
from report_agent.models.template import RenderContext
from report_agent.rendering.graphs.adapters import MatplotlibFigureExporter
from report_agent.rendering.graphs.renderer import GraphRenderer
from report_agent.rendering.images import ImageRenderer
from report_agent.rendering.tables import StylerTableRenderer


@pytest.mark.parametrize("suffix", [".png", ".jpg"])
def test_images_are_validated_staged_and_use_safe_paths(
    tmp_path: Path, suffix: str
) -> None:
    source = tmp_path / f"logo % & {{draft}}{suffix}"
    Image.new("RGB", (20, 20), "white").save(source)
    context = RenderContext(tmp_path / "workspace", "logo")
    result = ImageRenderer().render(
        ImageInput(source), InputDefinition(type="image", width="20mm"), context
    )
    assert result.assets[0].read_bytes() == source.read_bytes()
    assert source.name not in result.latex
    assert "width=20mm" in result.latex
    assert result.assets[0].is_relative_to(context.workspace)


def test_invalid_graphics_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "fake.png"
    source.write_bytes(b"not an image")
    with pytest.raises(OSError):
        ImageRenderer().render(
            ImageInput(source),
            InputDefinition(type="image"),
            RenderContext(tmp_path, "logo"),
        )


@pytest.mark.parametrize(
    "width", [r"1\linewidth}{\input{secret}", "0mm", "-3cm", "100%", "9" * 400 + "mm"]
)
def test_arbitrary_graphics_options_cannot_be_injected(width: str) -> None:
    with pytest.raises(ValidationError):
        InputDefinition(type="image", width=width)


def test_figure_and_graph_file_inputs_preserve_caller_figure(tmp_path: Path) -> None:
    figure = Figure(figsize=(4, 2), layout="constrained")
    axis = figure.subplots()
    (line,) = axis.plot([1, 2], [3, 5])
    axis.set_title("Revenue")
    sizes = figure.get_size_inches().copy()
    source = tmp_path / "original.pdf"
    figure.savefig(source)
    position = axis.get_position().bounds
    renderer = GraphRenderer(MatplotlibFigureExporter())
    definition = InputDefinition(type="graph", width=r"1\linewidth")
    for value in [FigureInput(figure), GraphInput(source)]:
        rendered = renderer.render(
            value, definition, RenderContext(tmp_path / "job", "trend")
        )
        assert rendered.assets[0].read_bytes().startswith(b"%PDF-")
    np.testing.assert_array_equal(figure.get_size_inches(), sizes)
    np.testing.assert_array_equal(line.get_ydata(), [3, 5])
    assert axis.get_title() == "Revenue"
    assert axis.get_position().bounds == position


def test_failed_figure_export_restores_axes_layout(tmp_path: Path, monkeypatch) -> None:
    figure = Figure(figsize=(4, 2), layout="constrained")
    axis = figure.subplots()
    axis.plot([1, 2], [3, 5])
    position = axis.get_position().bounds
    in_layout = axis.get_in_layout()

    def fail(*args, **kwargs):
        axis.set_position([0.2, 0.2, 0.5, 0.5])
        raise OSError("export failed")

    monkeypatch.setattr(figure, "savefig", fail)
    with pytest.raises(OSError, match="export failed"):
        MatplotlibFigureExporter().export(figure, tmp_path / "figure.pdf")
    assert axis.get_position().bounds == position
    assert axis.get_in_layout() == in_layout


def test_tables_escape_values_labels_and_preserve_dataframe(tmp_path: Path) -> None:
    frame = pd.DataFrame({"Revenue %": [12.5, np.nan], "Team": ["R&D", "Ops_1"]})
    frame.index = pd.Index(["A&B", "B_2"], name="Group & team")
    original = frame.copy(deep=True)
    result = StylerTableRenderer().render(
        TableInput(frame),
        InputDefinition(type="table"),
        RenderContext(tmp_path, "sales"),
    )
    for expected in [
        r"Revenue \%",
        r"R\&D",
        r"Ops\_1",
        r"A\&B",
        r"Group \& team",
        "--",
    ]:
        assert expected in result.latex
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize(
    "preset", ["financial", "comparison", "heatmap_sequential", "heatmap_diverging"]
)
def test_table_presets_and_longtable(tmp_path: Path, preset: str) -> None:
    frame = pd.DataFrame({"A": [-0.2, 0.8], "B": [0.4, 0.6]})
    result = StylerTableRenderer().render(
        TableInput(frame),
        InputDefinition(type="table", preset=preset, longtable=True),
        RenderContext(tmp_path, "table"),
    )
    assert r"\begin{longtable}" in result.latex
    assert r"\endhead" in result.latex
    if preset != "financial":
        assert r"\cellcolor" in result.latex


def test_invalid_and_empty_tables_are_rejected(tmp_path: Path) -> None:
    renderer = StylerTableRenderer()
    with pytest.raises(ValueError, match="non-empty"):
        renderer.render(
            TableInput(pd.DataFrame()),
            InputDefinition(type="table"),
            RenderContext(tmp_path, "t"),
        )


def test_heatmap_accepts_nullable_numbers_and_rejects_infinity(tmp_path: Path) -> None:
    renderer = StylerTableRenderer()
    definition = InputDefinition(type="table", preset="heatmap_sequential")
    frame = pd.DataFrame({"A": pd.array([1, pd.NA], dtype="Int64"), "B": [2.0, 3.0]})
    assert (
        "cellcolor"
        in renderer.render(
            TableInput(frame), definition, RenderContext(tmp_path, "t")
        ).latex
    )
    frame = pd.DataFrame({"A": [1.0, np.inf]})
    with pytest.raises(ValueError, match="infinite"):
        renderer.render(TableInput(frame), definition, RenderContext(tmp_path, "t"))
    with pytest.raises(ValueError, match="numeric"):
        renderer.render(
            TableInput(pd.DataFrame({"name": ["a"]})),
            InputDefinition(type="table", preset="heatmap_sequential"),
            RenderContext(tmp_path, "t"),
        )


def test_unset_precision_preserves_rates_and_integer_counts(tmp_path: Path) -> None:
    frame = pd.DataFrame({"rate": [0.123456789], "count": [12345]})
    result = StylerTableRenderer().render(
        TableInput(frame),
        InputDefinition(type="table", show_index=False),
        RenderContext(tmp_path, "t"),
    )
    assert "0.123456789" in result.latex
    assert "12,345" in result.latex
    assert "multirow" not in result.required_packages
