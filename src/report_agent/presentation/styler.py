"""Apply metadata styling to prepared text, images, graphs, and tables."""

from typing import Protocol

from report_agent.metadata.styles import PlaceholderStyle
from report_agent.models.results import RenderedContent
from report_agent.rendering.latex import escape_text


class PlaceholderStyler(Protocol):
    def apply(
        self, content: RenderedContent, style: PlaceholderStyle | None
    ) -> RenderedContent: ...


def _points(value: float) -> str:
    return format(value, ".6f").rstrip("0").rstrip(".")


class LatexPlaceholderStyler:
    """Build scoped commands; supplied content is already escaped/trusted."""

    def apply(
        self, content: RenderedContent, style: PlaceholderStyle | None
    ) -> RenderedContent:
        if style is None or style == PlaceholderStyle() or not content.latex:
            return content
        typography, layout = style.typography, style.layout
        declarations = []
        packages = set(content.required_packages)
        if typography.font_size_pt is not None:
            size = typography.font_size_pt
            leading = typography.line_height_pt or size * 1.2
            declarations.append(
                rf"\fontsize{{{_points(size)}}}{{{_points(leading)}}}\selectfont"
            )
        if typography.color is not None:
            declarations.append(rf"\color[HTML]{{{typography.color[1:].upper()}}}")
            packages.add("xcolor")
        if typography.bold is not None:
            declarations.append(r"\bfseries" if typography.bold else r"\mdseries")
        if typography.italic is not None:
            declarations.append(r"\itshape" if typography.italic else r"\upshape")
        if typography.paragraph_spacing_pt is not None:
            declarations.append(
                rf"\setlength{{\parskip}}{{{_points(typography.paragraph_spacing_pt)}pt}}"
            )
        if layout.display == "inline":
            latex = "{" + "".join(declarations) + " " + content.latex + "}"
            return RenderedContent(latex, content.assets, frozenset(packages))

        # Block alignment must finish its paragraph before leaving the scoped group.
        alignment = {
            "left": r"\raggedright",
            "center": r"\centering",
            "right": r"\raggedleft",
        }
        body = content.latex
        if layout.heading is not None:
            heading = layout.heading
            star = "" if heading.numbered else "*"
            body = (
                rf"\{heading.level}{star}{{{escape_text(heading.text)}}}" + "\n" + body
            )
        if declarations:
            body = "".join(declarations) + "\n" + body
        if style.container is not None:
            box = style.container
            packages.add("xcolor")
            inner_width = rf"\dimexpr{box.width}-2\fboxsep-2\fboxrule\relax"
            body = (
                rf"\setlength{{\fboxsep}}{{{_points(box.padding_pt)}pt}}"
                rf"\setlength{{\fboxrule}}{{{_points(box.border_width_pt)}pt}}"
                rf"\ifdim{inner_width}>0pt\relax"
                rf"\fcolorbox[HTML]{{{box.border_color[1:].upper()}}}"
                rf"{{{box.background_color[1:].upper()}}}"
                rf"{{\begin{{minipage}}[t]{{{inner_width}}}"
                + alignment.get(layout.alignment, "")
                + "\n"
                + body
                + r"\par\end{minipage}}"
                + r"\else\PackageError{report-agent}{Container has no usable width}"
                r"{Increase container width or reduce padding.}\fi"
            )
        before = "\\clearpage\n" if layout.page_break_before else ""
        after = "\n\\clearpage" if layout.page_break_after else ""
        align = alignment.get(layout.alignment, "")
        latex = (
            before
            + "\\par\n\\begingroup\n"
            + (
                rf"\vspace{{{_points(layout.space_before_pt)}pt}}"
                if layout.space_before_pt
                else ""
            )
            + align
            + "\n"
            + body
            + "\n\\par\n\\endgroup\n"
            + (
                rf"\vspace{{{_points(layout.space_after_pt)}pt}}"
                if layout.space_after_pt
                else ""
            )
            + after
        )
        return RenderedContent(latex, content.assets, frozenset(packages))
