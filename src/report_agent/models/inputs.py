"""Typed values supplied by callers for one report."""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from matplotlib.figure import Figure
    from pandas import DataFrame


@dataclass(frozen=True)
class TextInput:
    text: str


@dataclass(frozen=True)
class ImageInput:
    path: Path


@dataclass(frozen=True)
class GraphInput:
    """An existing graph stored as a supported image or PDF file."""

    path: Path


@dataclass(frozen=True)
class FigureInput:
    """A caller-owned figure; export preserves its dimensions and axes layout."""

    figure: "Figure"


@dataclass(frozen=True)
class TableInput:
    data: "DataFrame"


@dataclass(frozen=True)
class AnimationInput:
    """Finite encoded animation and its static preview; paths must outlive rendering."""

    path: Path
    poster_path: Path


type ContentInput = (
    AnimationInput | TextInput | ImageInput | GraphInput | FigureInput | TableInput
)
