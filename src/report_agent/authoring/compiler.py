"""Application-owned source generation. User/model text stays in typed slots."""

from pathlib import Path
from xml.etree import ElementTree as ET

import yaml

from report_agent.metadata.loader import MetadataLoader
from report_agent.templates.odf import q


def compile_template(definition, directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    layout = definition.layout
    inputs = {"title": {"type": "text", "default": layout.title, "max_chars": 200}}
    for block in layout.blocks:
        inputs[f"heading_{block.name}"] = {
            "type": "text",
            "default": block.heading,
            "max_chars": 120,
        }
        inputs[block.name] = {"type": "graph" if block.kind == "chart" else block.kind}
        if block.kind == "text":
            inputs[block.name].update(default=block.text, max_chars=block.max_chars)
        if layout.format == "pdf":
            if block.kind == "table":
                inputs[block.name].update(
                    backend="styler", show_index=False, longtable=True
                )
            elif block.kind == "chart":
                inputs[block.name]["width"] = r"0.95\linewidth"
    if layout.format == "pdf":
        entrypoint = "main.tex"
        metadata = {
            "schema_version": 1,
            "id": definition.id,
            "entrypoint": entrypoint,
            "compiler": {"engine": "pdflatex"},
            "inputs": inputs,
        }
        source = _latex(layout)
    else:
        entrypoint = (
            "main." + {"docx": "fodt", "pptx": "fodp", "xlsx": "fods"}[layout.format]
        )
        metadata = {
            "schema_version": 2,
            "id": definition.id,
            "entrypoint": entrypoint,
            "document": {"engine": "libreoffice", "format": layout.format},
            "inputs": inputs,
        }
        source = _office(layout)
    MetadataLoader().load(metadata)
    (directory / entrypoint).write_text(source)
    (directory / "template.yaml").write_text(yaml.safe_dump(metadata, sort_keys=False))
    return metadata


def _latex(layout):
    geometry = "margin=1in" + (
        ",landscape" if layout.orientation == "landscape" else ""
    )
    source = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{lmodern}",
        rf"\usepackage[{geometry}]{{geometry}}",
        r"\usepackage{graphicx,xcolor,booktabs,longtable,array,multirow}",
        r"\setlength{\parindent}{0pt}",
        r"\setlength{\parskip}{0.65em}",
        rf"\definecolor{{accent}}{{HTML}}{{{layout.accent[1:]}}}",
    ]
    if layout.font == "sans":
        source.append(r"\renewcommand{\familydefault}{\sfdefault}")
    source.extend(
        [r"\begin{document}", r"{\LARGE\bfseries\color{accent} <<title>>}\par"]
    )
    for block in layout.blocks:
        if block.page_break_before:
            source.append(r"\clearpage")
        source.extend(
            [
                rf"\section*{{\color{{accent}} <<heading_{block.name}>>}}",
                f"<<{block.name}>>",
            ]
        )
    source.append(r"\end{document}")
    return "\n".join(source)


def _element(parent, tag, attrs=None, text=None):
    node = ET.SubElement(parent, q(tag), {q(k): v for k, v in (attrs or {}).items()})
    node.text = text
    return node


def _slot(parent, kind, name, **attrs):
    return ET.SubElement(parent, q(f"ra:{kind}"), {"name": name, **attrs})


def _office(layout):
    fmt = layout.format
    kind = {"docx": "text", "pptx": "presentation", "xlsx": "spreadsheet"}[fmt]
    root = ET.Element(
        q("office:document"),
        {
            q("office:version"): "1.3",
            q("office:mimetype"): f"application/vnd.oasis.opendocument.{kind}",
        },
    )
    font = "Liberation Sans" if layout.font == "sans" else "Liberation Serif"
    fonts = _element(root, "office:font-face-decls")
    _element(fonts, "style:font-face", {"style:name": font, "svg:font-family": font})
    styles = _element(root, "office:styles")
    auto = _element(root, "office:automatic-styles")
    for name, size, color in [
        ("Body", "18pt" if fmt == "pptx" else "11pt", "#252525"),
        ("Heading", "24pt" if fmt == "pptx" else "16pt", layout.accent),
        ("Title", "32pt" if fmt == "pptx" else "26pt", layout.accent),
        ("TableText", "15pt" if fmt == "pptx" else "10pt", "#252525"),
        ("HeaderText", "15pt" if fmt == "pptx" else "10pt", "#FFFFFF"),
    ]:
        style = _element(
            styles if fmt == "docx" else auto,
            "style:style",
            {"style:name": name, "style:family": "paragraph"},
        )
        _element(
            style,
            "style:text-properties",
            {
                "fo:font-size": size,
                "fo:font-family": font,
                "style:font-name": font,
                "fo:color": color,
                "fo:font-weight": "normal" if name in {"Body", "TableText"} else "bold",
            },
        )
        _element(style, "style:paragraph-properties", {"fo:margin-bottom": "0.3cm"})
    for name, color in [("TableHeader", layout.accent), ("TableBody", "#FFFFFF")]:
        style = _element(
            styles if fmt == "pptx" else auto,
            "style:style",
            {"style:name": name, "style:family": "table-cell"},
        )
        _element(
            style,
            "style:table-cell-properties",
            {
                "fo:background-color": color,
                "fo:padding": "0.12cm",
                "fo:wrap-option": "wrap",
                "fo:border": "0.5pt solid #D8DDE3",
            },
        )
        _element(
            style,
            "style:text-properties",
            {
                "fo:color": "#FFFFFF" if name == "TableHeader" else "#252525",
                "fo:font-size": "12pt" if fmt == "pptx" else "10pt",
                "style:font-name": font,
            },
        )
        if fmt == "pptx":
            ET.SubElement(
                style,
                "{urn:org:documentfoundation:names:experimental:office:xmlns:loext:1.0}graphic-properties",
                {q("draw:fill"): "solid", q("draw:fill-color"): color},
            )
    col = _element(
        auto,
        "style:style",
        {"style:name": "WideColumn", "style:family": "table-column"},
    )
    _element(col, "style:table-column-properties", {"style:column-width": "12cm"})
    for name, size in [("CellTitle", "22pt"), ("CellHeading", "14pt")]:
        cell_style = _element(
            auto,
            "style:style",
            {
                "style:name": name,
                "style:family": "table-cell",
            },
        )
        _element(
            cell_style,
            "style:table-cell-properties",
            {
                "fo:wrap-option": "wrap",
                "fo:padding": "0.15cm",
            },
        )
        _element(
            cell_style,
            "style:text-properties",
            {
                "style:font-name": font,
                "fo:font-size": size,
                "fo:font-weight": "bold",
                "fo:color": layout.accent,
            },
        )
    frame_style = _element(
        auto,
        "style:style",
        {
            "style:name": "TextFrame",
            "style:family": "graphic",
        },
    )
    _element(
        frame_style,
        "style:graphic-properties",
        {
            "draw:stroke": "none",
            "draw:fill": "none",
            "fo:padding": "0cm",
            "draw:textarea-vertical-align": "top",
        },
    )
    if fmt == "pptx":
        table_template = _element(
            styles, "table:table-template", {"table:name": "ReportTable"}
        )
        for tag, style_name in [
            ("body", "TableBody"),
            ("first-row", "TableHeader"),
            ("odd-rows", "TableBody"),
            ("even-rows", "TableBody"),
        ]:
            _element(table_template, f"table:{tag}", {"table:style-name": style_name})
    page = _element(auto, "style:page-layout", {"style:name": "Page"})
    width, height = (
        ("29.7cm", "21cm") if layout.orientation == "landscape" else ("21cm", "29.7cm")
    )
    if fmt == "pptx":
        width, height = "28cm", "15.75cm"
    _element(
        page,
        "style:page-layout-properties",
        {
            "fo:page-width": width,
            "fo:page-height": height,
            "fo:margin": "1.5cm",
            "style:print-orientation": "landscape"
            if fmt == "pptx"
            else layout.orientation,
        },
    )
    masters = _element(root, "office:master-styles")
    _element(
        masters,
        "style:master-page",
        {"style:name": "Default", "style:page-layout-name": "Page"},
    )
    body = _element(_element(root, "office:body"), f"office:{kind}")
    if fmt == "docx":
        _slot(_element(body, "text:p", {"text:style-name": "Title"}), "text", "title")
        for block in layout.blocks:
            heading_attrs = {"text:style-name": "Heading", "text:outline-level": "1"}
            if block.page_break_before:
                style = _element(
                    auto,
                    "style:style",
                    {
                        "style:name": f"Break_{block.name}",
                        "style:family": "paragraph",
                        "style:parent-style-name": "Heading",
                    },
                )
                _element(
                    style, "style:paragraph-properties", {"fo:break-before": "page"}
                )
                heading_attrs["text:style-name"] = f"Break_{block.name}"
            _slot(
                _element(body, "text:h", heading_attrs), "text", f"heading_{block.name}"
            )
            if block.kind == "text":
                _slot(body, "paragraphs", block.name, **{"style-name": "Body"})
            elif block.kind == "table":
                _table_slot(body, block.name)
            else:
                _slot(
                    _element(body, "text:p"),
                    "image",
                    block.name,
                    width="17cm",
                    height="9cm",
                )
    elif fmt == "pptx":
        page = _element(
            body,
            "draw:page",
            {"draw:name": "Title", "draw:master-page-name": "Default"},
        )
        _slide_text(page, "title", "Title", "4cm", "6cm")
        for i, block in enumerate(layout.blocks):
            page = _element(
                body,
                "draw:page",
                {"draw:name": f"Slide {i + 2}", "draw:master-page-name": "Default"},
            )
            _slide_text(page, f"heading_{block.name}", "Heading", "1cm", "2cm")
            if block.kind == "text":
                _slide_text(page, block.name, "Body", "3.5cm", "10cm")
            elif block.kind == "table":
                frame = _frame(page, block.name, "3.5cm", "10cm")
                _table_slot(frame, block.name)
            else:
                _slot(
                    page,
                    "image",
                    block.name,
                    x="1.5cm",
                    y="3.5cm",
                    width="25cm",
                    height="10cm",
                )
    else:
        sheet = _element(body, "table:table", {"table:name": "Report"})
        _element(sheet, "table:table-column", {"table:style-name": "WideColumn"})
        _cell_row(sheet, "title")
        for block in layout.blocks:
            _cell_row(sheet, f"heading_{block.name}")
            if block.kind == "text":
                _cell_row(sheet, block.name)
            else:
                _table_slot(body, block.name, **{"sheet-name": f"Data_{len(body)}"})
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


def _table_slot(parent, name, **attrs):
    if parent.tag == q("draw:frame"):
        attrs["table-template-name"] = "ReportTable"
    return _slot(
        parent,
        "table",
        name,
        **{
            "header-cell-style-name": "TableHeader",
            "body-cell-style-name": "TableBody",
            "header-paragraph-style-name": "HeaderText",
            "body-paragraph-style-name": "TableText",
            **attrs,
        },
    )


def _frame(page, name, y, height):
    return _element(
        page,
        "draw:frame",
        {
            "draw:name": name,
            "draw:style-name": "TextFrame",
            "svg:x": "1.5cm",
            "svg:y": y,
            "svg:width": "25cm",
            "svg:height": height,
        },
    )


def _slide_text(page, name, style, y, height):
    box = _element(_frame(page, name, y, height), "draw:text-box")
    _slot(_element(box, "text:p", {"text:style-name": style}), "text", name)


def _cell_row(sheet, name):
    row = _element(sheet, "table:table-row")
    style = (
        "CellTitle"
        if name == "title"
        else ("CellHeading" if name.startswith("heading_") else "TableBody")
    )
    cell = _element(row, "table:table-cell", {"table:style-name": style})
    _slot(cell, "cell", name)
