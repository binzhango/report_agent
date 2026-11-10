"""Validate the small TeX dimension vocabulary accepted by metadata."""

import re
from math import isfinite


def validate_dimension(value: str) -> str:
    match = re.fullmatch(
        r"([0-9]+(?:\.[0-9]+)?)(?:mm|cm|in|pt|em|ex|\\linewidth|\\textwidth|\\columnwidth)",
        value,
    )
    if (
        match is None
        or not isfinite(float(match.group(1)))
        or float(match.group(1)) <= 0
    ):
        raise ValueError("Use a positive TeX dimension, e.g. 25mm or 0.9\\linewidth.")
    return value
