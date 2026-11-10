"""Dependencies and overflow must produce actionable input-level diagnostics."""

from pathlib import Path

import pytest

from report_agent.compilation.diagnostics import compile_warnings
from report_agent.metadata.models import InputDefinition
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
    assert loaded == {"xcolor", "graphicx", "booktabs", "custom", "multirow"}


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
