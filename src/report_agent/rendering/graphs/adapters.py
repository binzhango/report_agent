"""Graph export extension boundary and matplotlib PDF exporter."""

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from matplotlib.figure import Figure


class FigureExporter(Protocol):
    def export(self, figure: "Figure", destination: Path) -> Path: ...


class MatplotlibFigureExporter:
    def export(self, figure: "Figure", destination: Path) -> Path:
        """Export without closing the figure or changing its plot layout.

        Drawing can populate Matplotlib caches. Restore visible layout/state
        instead of deep-copying arbitrary artist/callback graphs.
        """
        from matplotlib.figure import Figure

        if not isinstance(figure, Figure):
            raise ValueError("FigureInput requires a matplotlib Figure.")
        if any(
            text.get_usetex()
            for text in figure.findobj()
            if hasattr(text, "get_usetex")
        ):
            raise ValueError(
                "matplotlib usetex is not supported; pass a pre-rendered graph instead."
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        size = figure.get_size_inches().copy()
        axes = [
            (
                axis,
                axis.get_position(original=True).frozen(),
                axis.get_position().frozen(),
                axis.get_in_layout(),
            )
            for axis in figure.axes
        ]
        subplot = {
            name: getattr(figure.subplotpars, name)
            for name in ("left", "right", "bottom", "top", "wspace", "hspace")
        }
        stale = [(artist, artist.stale) for artist in figure.findobj()]
        try:
            figure.savefig(
                destination,
                format="pdf",
                metadata={"CreationDate": None, "ModDate": None},
            )
        finally:
            figure.set_size_inches(size, forward=False)
            figure.subplotpars.update(**subplot)
            for axis, original, active, in_layout in axes:
                axis.set_position(original, which="original")
                axis.set_position(active, which="active")
                axis.set_in_layout(in_layout)
            for artist, was_stale in stale:
                artist.stale = was_stale
        return destination
