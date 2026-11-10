"""Dependencies and overflow must produce actionable input-level diagnostics."""

from pathlib import Path

import pytest

from report_agent.compilation.diagnostics import compile_warnings
from report_agent.metadata.models import CompilerOptions, InputDefinition
from report_agent.models.template import TemplateBundle
from report_agent.rendering.registry import RendererRegistry
from report_agent.rendering.text import TextRenderer
from report_agent.validation.packages import TemplatePackageScanner


def test_package_scanner_follows_local_class_style_and_inputs(tmp_path: Path) -> None:
    source = r"""\documentclass{local}
% \usepackage{fake}
\usepackage[table]{xcolor,graphicx}
\begin{verbatim}\usepackage{notloaded}\end{verbatim}
\input{header}
"""
    (tmp_path / "local.cls").write_text(r"\RequirePackage{booktabs}")
    (tmp_path / "header.tex").write_text(r"\usepackage{custom}")
    (tmp_path / "custom.sty").write_text(r"\RequirePackage{multirow}")
    loaded = TemplatePackageScanner().loaded(
        TemplateBundle(tmp_path, tmp_path / "main.tex"), source
    )
    assert loaded == {
        "xcolor",
        "colortbl",
        "graphicx",
        "booktabs",
        "custom",
        "multirow",
    }


@pytest.mark.parametrize(
    "declaration, expected",
    [
        (r"\usepackage{xcolor}", {"xcolor"}),
        (r"\RequirePackage[ dvipsnames, table ]{xcolor}", {"xcolor", "colortbl"}),
        (r"\usepackage{colortbl}", {"colortbl"}),
        (r"\usepackage[notable]{xcolor}", {"xcolor"}),
        (
            r"\PassOptionsToPackage{table}{xcolor}\usepackage{xcolor}",
            {"xcolor", "colortbl"},
        ),
        (
            r"\usepackage{xcolor}\PassOptionsToPackage{table}{xcolor}",
            {"xcolor"},
        ),
        (r"\usepackage{xcolor}\usepackage[table]{xcolor}", {"xcolor"}),
        (r"\documentclass[table]{article}\usepackage{xcolor}", {"xcolor", "colortbl"}),
        (r"\documentclass[table]{article}", set()),
        (r"\PassOptionsToPackage{table}{other}\usepackage{xcolor}", {"xcolor"}),
        (
            "% "
            + r"\PassOptionsToPackage{table}{xcolor}"
            + "\n"
            + r"\usepackage{xcolor}",
            {"xcolor"},
        ),
        (
            r"\begin{verbatim}\PassOptionsToPackage{table}{xcolor}\end{verbatim}\usepackage{xcolor}",
            {"xcolor"},
        ),
    ],
)
def test_cell_color_dependency_requires_table_option_or_explicit_package(
    tmp_path: Path, declaration: str, expected: set[str]
) -> None:
    loaded = TemplatePackageScanner().loaded(
        TemplateBundle(tmp_path, tmp_path / "main.tex"), declaration
    )
    assert loaded == expected


@pytest.mark.parametrize(
    "source, expected",
    [
        (r"\input{options}\documentclass{theme}", {"xcolor", "colortbl"}),
        (r"\documentclass{theme}\input{options}", {"xcolor"}),
        (r"\documentclass{theme}\PassOptionsToPackage{table}{xcolor}", {"xcolor"}),
    ],
)
def test_xcolor_options_follow_local_dependency_order(
    tmp_path, source, expected
) -> None:
    (tmp_path / "theme.cls").write_text(r"\LoadClass{article}\RequirePackage{xcolor}")
    (tmp_path / "options.tex").write_text(r"\PassOptionsToPackage{table}{xcolor}")
    loaded = TemplatePackageScanner().loaded(
        TemplateBundle(tmp_path, tmp_path / "main.tex"),
        source,
    )
    assert loaded == expected


def test_registry_separates_table_backends() -> None:
    first, second = TextRenderer(), TextRenderer()
    registry = RendererRegistry(
        {("table", "styler"): first, ("table", "great_tables"): second}
    )
    assert registry.get("table") is first
    assert registry.get("table", "great_tables") is second
    with pytest.raises(ValueError, match="not implemented"):
        InputDefinition(
            type="table", backend="great_tables", preset="heatmap_sequential"
        )


def test_table_overflow_is_promoted_but_other_warnings_are_retained() -> None:
    source = (
        "before\n% REPORT_AGENT_TABLE_BEGIN sales\nbody\n"
        "% REPORT_AGENT_TABLE_END sales\nafter"
    )
    result = compile_warnings(
        r"Overfull \hbox (20.0pt too wide) in alignment at lines 2--4"
        + "\nLaTeX Warning: test",
        source,
    )
    assert result[0].code == "table_overflow" and result[0].severity == "error"
    assert result[0].input_name == "sales"
    assert result[1].severity == "warning"


@pytest.mark.parametrize(
    "width, tolerance, severity",
    [
        ("0.4", 2, "warning"),
        ("2", 2, "warning"),
        ("2.01", 2, "error"),
        ("0.4", 0, "error"),
        ("4.5", 5, "warning"),
    ],
)
def test_table_overflow_tolerance(width, tolerance, severity) -> None:
    source = "% REPORT_AGENT_TABLE_BEGIN sales\nbody\n% REPORT_AGENT_TABLE_END sales"
    result = compile_warnings(
        rf"Overfull \hbox ({width}pt too wide) in alignment at lines 1--3",
        source,
        table_overflow_tolerance_pt=tolerance,
    )
    assert result[0].code == "table_overflow"
    assert result[0].severity == severity


@pytest.mark.parametrize("tolerance", [-1, float("inf"), float("nan")])
def test_invalid_overflow_tolerance_is_rejected(tolerance) -> None:
    with pytest.raises(ValueError):
        CompilerOptions(table_overflow_tolerance_pt=tolerance)
