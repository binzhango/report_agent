"""Plain-text escaping shared by content strategies."""

_SPECIAL = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "#": r"\#",
    "%": r"\%",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def escape_text(text: str) -> str:
    """Preserve paragraphs; a single newline acts as a space, as in LaTeX."""
    if any(ord(char) < 32 and char not in "\n\r\t" for char in text):
        raise ValueError("Text contains unsupported control characters.")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return "".join(_SPECIAL.get(char, char) for char in normalized)
