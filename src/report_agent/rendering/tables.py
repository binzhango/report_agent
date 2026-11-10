"""Render DataFrames as native LaTeX tables using Styler."""

import numpy as np
import pandas as pd

from report_agent.metadata.models import InputDefinition
from report_agent.models.inputs import ContentInput, TableInput
from report_agent.models.results import RenderedContent
from report_agent.models.template import RenderContext
from report_agent.rendering.latex import escape_text


class StylerTableRenderer:
    def render(
        self,
        value: ContentInput,
        definition: InputDefinition,
        context: RenderContext,
    ) -> RenderedContent:
        """Render DataFrames as native LaTeX tables using Styler."""
        if not isinstance(value, TableInput) or definition.type != "table":
            raise ValueError(
                "Table renderer requires TableInput and a table declaration."
            )
        frame = value.data
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            raise ValueError("TableInput requires a non-empty pandas DataFrame.")
        # Work on a copy so caller-owned labels and values remain unchanged.
        frame = frame.copy(deep=True)
        frame.index = frame.index.set_names(
            [
                escape_text(str(name)) if name is not None else None
                for name in frame.index.names
            ]
        )
        frame.columns = frame.columns.set_names(
            [
                escape_text(str(name)) if name is not None else None
                for name in frame.columns.names
            ]
        )
        style = (
            frame.style.format(
                precision=definition.precision
                if definition.precision is not None
                else 1,
                thousands=",",
                na_rep="--",
                escape="latex",
            )
            .format_index(escape="latex", axis=0)
            .format_index(escape="latex", axis=1)
        )
        if definition.show_index is False:
            style = style.hide(axis="index")
        numeric = frame.select_dtypes(include="number").columns
        preset = definition.preset or "financial"
        packages = {"booktabs", "multirow"}
        if preset.startswith("heatmap"):
            if len(numeric) != len(frame.columns):
                raise ValueError("Heatmap tables require numeric columns only.")
            values = frame.to_numpy(dtype=float, na_value=np.nan)
            if np.isinf(values).any():
                raise ValueError("Heatmap tables cannot contain infinite values.")
            if not np.isfinite(values).any():
                raise ValueError("Heatmap tables require at least one finite value.")
            kwargs = {"vmin": -1, "vmax": 1} if preset == "heatmap_diverging" else {}
            style = style.background_gradient(
                axis=None,
                cmap="RdBu" if preset == "heatmap_diverging" else "Blues",
                **kwargs,
            )
            packages.add("xcolor")
        elif preset == "comparison" and len(numeric):
            style = style.highlight_max(subset=numeric, axis=0, color="#dcece8")
            packages.add("xcolor")
        if preset != "financial" and (
            not frame.index.is_unique or not frame.columns.is_unique
        ):
            raise ValueError("Styled tables require unique row and column labels.")
        latex = style.to_latex(
            hrules=True,
            convert_css=True,
            multirow_align="t",
            multicol_align="c",
            environment="longtable" if definition.longtable else None,
        )
        if definition.longtable:
            packages.add("longtable")
        return RenderedContent(latex, required_packages=frozenset(packages))
