"""Shared presentation must be independent of the underlying content adapter."""

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from report_agent.metadata.loader import MetadataLoader
from report_agent.metadata.models import InputDefinition
from report_agent.metadata.styles import PlaceholderStyle
from report_agent.models.results import RenderedContent
from report_agent.presentation.styler import LatexPlaceholderStyler


@pytest.mark.parametrize(
    "latex",
    ["Plain text", r"\includegraphics{a.pdf}", r"\begin{tabular}{r}1\\\end{tabular}"],
)
def test_common_styles_preserve_content_assets_and_requirements(latex: str) -> None:
    source = RenderedContent(latex, (Path("a.pdf"),), frozenset({"graphicx"}))
    styled = LatexPlaceholderStyler().apply(
        source,
        PlaceholderStyle.model_validate(
            {
                "typography": {"color": "#087e8b", "font_size_pt": 11, "bold": True},
            }
        ),
    )
    assert source.latex in styled.latex
    assert r"\color[HTML]{087E8B}" in styled.latex
    assert r"\bfseries" in styled.latex
    assert styled.assets == source.assets
    assert styled.required_packages == {"graphicx", "xcolor"}


def test_block_container_and_heading_are_scoped_and_escaped() -> None:
    style = PlaceholderStyle.model_validate(
        {
            "typography": {
                "font_size_pt": 12,
                "line_height_pt": 16,
                "paragraph_spacing_pt": 6,
            },
            "layout": {
                "display": "block",
                "alignment": "right",
                "space_before_pt": 4,
                "space_after_pt": 8,
                "page_break_before": True,
                "heading": {"text": "R&D 12%", "level": "subsection"},
            },
            "container": {"width": r"0.8\linewidth", "background_color": "#F0F0F0"},
        }
    )
    result = LatexPlaceholderStyler().apply(RenderedContent("Body"), style)
    assert result.latex.startswith("\\clearpage\n\\par\n\\begingroup")
    assert r"\subsection*{R\&D 12\%}" in result.latex
    assert r"\raggedleft" in result.latex
    assert r"\setlength{\parskip}{6pt}" in result.latex
    assert r"\begin{minipage}" in result.latex
    assert result.latex.endswith(r"\vspace{8pt}")
    assert r"\par\end{minipage}" in result.latex
    assert "\\par\n\\endgroup" in result.latex


@pytest.mark.parametrize("style", [None, PlaceholderStyle()])
def test_absent_or_empty_style_is_an_exact_noop(style) -> None:
    original = RenderedContent("Plain text")
    assert LatexPlaceholderStyler().apply(original, style) is original


def test_empty_optional_content_does_not_emit_heading_spacing_or_box() -> None:
    style = PlaceholderStyle.model_validate(
        {
            "layout": {
                "display": "block",
                "page_break_before": True,
                "heading": {"text": "Optional section"},
            },
            "container": {},
        }
    )
    assert LatexPlaceholderStyler().apply(RenderedContent(""), style).latex == ""


@pytest.mark.parametrize(
    "style",
    [
        {"typography": {"color": r"red}\input{secret}"}},
        {"typography": {"font_size_pt": float("nan")}},
        {"typography": {"font_size_pt": -10}},
        {"typography": {"line_height_pt": 14}},
        {"layout": {"alignment": "center"}},
        {"layout": {"heading": {"text": "Heading", "level": "input"}}},
        {"container": {}},
        {
            "layout": {"display": "block"},
            "container": {"width": r"1\linewidth}\input{x}"},
        },
    ],
)
def test_invalid_styles_are_rejected(style) -> None:
    with pytest.raises(ValidationError):
        PlaceholderStyle.model_validate(style)


def test_paginated_tables_require_breakable_style() -> None:
    assert (
        InputDefinition(type="table", longtable=True, style={}).style
        == PlaceholderStyle()
    )
    with pytest.raises(ValidationError, match="unbreakable"):
        InputDefinition(
            type="table",
            longtable=True,
            style={
                "layout": {"display": "block"},
                "container": {},
            },
        )
    value = InputDefinition(
        type="table",
        longtable=True,
        style={
            "layout": {"display": "block"},
            "typography": {"font_size_pt": 9},
        },
    )
    assert value.style.container is None


def test_json_and_yaml_resolve_style_using_same_placeholder_key(tmp_path: Path) -> None:
    metadata = {
        "id": "styled",
        "inputs": {
            "summary": {
                "type": "text",
                "style": {"typography": {"bold": True}},
            }
        },
    }
    json_path, yaml_path = tmp_path / "template.json", tmp_path / "template.yaml"
    json_path.write_text(json.dumps(metadata))
    yaml_path.write_text(yaml.safe_dump(metadata))
    loader = MetadataLoader()
    assert loader.load(json_path) == loader.load(yaml_path)
    assert loader.load(yaml_path).inputs["summary"].style.typography.bold


def test_style_does_not_change_input_text_escaping_contract() -> None:
    # The shared layer receives trusted fragments and must not escape them again.
    content = RenderedContent(r"Revenue \& costs")
    result = LatexPlaceholderStyler().apply(
        content,
        PlaceholderStyle.model_validate(
            {
                "typography": {"italic": True},
            }
        ),
    )
    assert r"Revenue \& costs" in result.latex
    assert r"\textbackslash" not in result.latex
