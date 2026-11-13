"""XML-aware ODF expansion. Caller data never becomes XML source."""

import base64
import hashlib
import math
import re
from datetime import date, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd
from defusedxml import ElementTree as safe_xml
from defusedxml.common import DefusedXmlException
from PIL import Image

from report_agent.models.inputs import (
    AnimationInput,
    FigureInput,
    TableInput,
    TextInput,
)

NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "svg": "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0",
    "xlink": "http://www.w3.org/1999/xlink",
    "presentation": "urn:oasis:names:tc:opendocument:xmlns:presentation:1.0",
    "ra": "urn:report-agent:template:1",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def q(name):
    prefix, local = name.split(":")
    return f"{{{NS[prefix]}}}{local}"


def parse(source):
    try:
        return safe_xml.fromstring(
            source, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
    except (DefusedXmlException, ET.ParseError) as exc:
        raise ValueError(f"Invalid XML: {exc}") from exc


def dimension(value):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(cm|mm|in|pt)", value or "")
    if not match or float(match[1]) <= 0:
        raise ValueError("Dimensions must be positive physical units (cm/mm/in/pt).")
    return value


def plain(element, value):
    text = str(value)
    if any(ord(c) < 32 and c not in "\n\r\t" for c in text):
        raise ValueError("Text contains XML control characters.")
    # ODF explicitly represents repeated spaces, tabs and line breaks.
    for part in re.split(r"( +|\t|\n)", text.replace("\r\n", "\n").replace("\r", "\n")):
        if not part:
            continue
        if part.isspace():
            if part == "\n":
                ET.SubElement(element, q("text:line-break"))
            elif part == "\t":
                ET.SubElement(element, q("text:tab"))
            else:
                ET.SubElement(element, q("text:s"), {q("text:c"): str(len(part))})
        elif len(element):
            element[-1].tail = (element[-1].tail or "") + part
        else:
            element.text = (element.text or "") + part


class OdfTemplate:
    def __init__(self, source: str, fmt: str):
        self.root = parse(source)
        self.fmt = fmt
        self.media = []
        self.media_info = []
        self.assets = []
        self.styles = {
            e.get(q("style:name"))
            for e in self.root.iter()
            if e.tag == q("style:style")
        }
        if self.root.tag != q("office:document"):
            raise ValueError("Expected a Flat ODF office:document root.")
        expected = {
            "docx": "office:text",
            "xlsx": "office:spreadsheet",
            "pptx": "office:presentation",
        }[fmt]
        if self.root.find(f"office:body/{expected}", NS) is None:
            raise ValueError("ODF body does not match output format.")
        for e in self.root.iter():
            if e.tag == q("office:scripts") and (len(e) or e.text and e.text.strip()):
                raise ValueError("Executable template content is unsupported.")
            if e.tag in {q("draw:object"), q("draw:object-ole"), q("draw:plugin")}:
                raise ValueError("Embedded executable/linked objects are unsupported.")
            if e.get(q("xlink:href")):
                raise ValueError(
                    "External template references are unsupported; embed assets."
                )

    def slots(self):
        return [
            (e.get("name"), e.tag.split("}")[-1])
            for e in self.root.iter()
            if e.tag.startswith("{" + NS["ra"] + "}")
        ]

    def expand(self, inputs, definitions, workspace):
        self.workspace = workspace
        sheet_names = [e.get(q("table:name")) for e in self.root.iter(q("table:table"))]
        for e in self.root.iter():
            if e.tag == q("ra:table") and self.fmt == "xlsx":
                sheet_names.append(e.get("sheet-name", e.get("name")))
        if len(sheet_names) != len(set(sheet_names)):
            raise ValueError("Duplicate table/sheet names.")
        for parent in list(self.root.iter()):
            for slot in list(parent):
                if not slot.tag.startswith("{" + NS["ra"] + "}"):
                    continue
                name, kind = slot.get("name"), slot.tag.split("}")[-1]
                value = inputs.get(name)
                if value is None:
                    default = definitions[name].default
                    value = TextInput(default) if default is not None else None
                nodes = [] if value is None else self._nodes(parent, slot, kind, value)
                index = list(parent).index(slot)
                tail = slot.tail
                parent.remove(slot)
                for offset, node in enumerate(nodes):
                    parent.insert(index + offset, node)
                if tail:
                    if nodes:
                        nodes[-1].tail = (nodes[-1].tail or "") + tail
                    elif index:
                        parent[index - 1].tail = (parent[index - 1].tail or "") + tail
                    else:
                        parent.text = (parent.text or "") + tail
        if any(e.tag.startswith("{" + NS["ra"] + "}") for e in self.root.iter()):
            raise ValueError("Unexpanded nested slots.")
        if self.fmt == "xlsx":
            # Source caches may predate runtime values, especially on forward tabs.
            # Omitting cached results makes Calc evaluate the formula on import.
            for cell in self.root.iter(q("table:table-cell")):
                if cell.get(q("table:formula")):
                    for attr in (
                        "office:value",
                        "office:string-value",
                        "office:boolean-value",
                        "office:date-value",
                    ):
                        cell.attrib.pop(q(attr), None)
                    for child in list(cell):
                        if child.tag == q("text:p"):
                            cell.remove(child)
        if any(
            e.get(q("table:formula"), "").startswith("of:") for e in self.root.iter()
        ):
            self.root.set("xmlns:of", "urn:oasis:names:tc:opendocument:xmlns:of:1.2")
        return ET.tostring(self.root, encoding="unicode")

    def style(self, node, attr):
        name = node.get(attr)
        if name and name not in self.styles:
            raise ValueError(f"Missing style: {name}")
        return name

    def _nodes(self, parent, slot, kind, value):
        if kind in {"text", "paragraphs"}:
            if not isinstance(value, TextInput):
                raise ValueError("Text slot requires TextInput.")
            if kind == "text":
                if parent.tag not in {q("text:p"), q("text:h"), q("text:span")}:
                    raise ValueError(
                        "Inline text requires paragraph/heading/span parent."
                    )
                node = ET.Element(q("text:span"))
                plain(node, " ".join(value.text.splitlines()))
                return [node]
            if parent.tag != q("office:text"):
                raise ValueError("Paragraph blocks require Writer document flow.")
            style = self.style(slot, "style-name")
            result = []
            for paragraph in re.split(r"\n\s*\n", value.text.replace("\r\n", "\n")):
                node = ET.Element(
                    q("text:p"), {q("text:style-name"): style} if style else {}
                )
                plain(node, paragraph)
                result.append(node)
            return result
        if kind == "cell":
            if (
                self.fmt != "xlsx"
                or parent.tag != q("table:table-cell")
                or not isinstance(value, TextInput)
            ):
                raise ValueError("Scalar cell slots require Calc cells and TextInput.")
            for attribute in (
                "table:formula",
                "office:value",
                "office:date-value",
                "office:boolean-value",
                "office:string-value",
            ):
                parent.attrib.pop(q(attribute), None)
            parent.set(q("office:value-type"), "string")
            node = ET.Element(q("text:p"))
            plain(node, value.text)
            return [node]
        if kind == "table":
            if not isinstance(value, TableInput) or not isinstance(
                value.data, pd.DataFrame
            ):
                raise ValueError("Table slots require TableInput(DataFrame).")
            frame = value.data
            if isinstance(frame.index, pd.MultiIndex) or isinstance(
                frame.columns, pd.MultiIndex
            ):
                raise ValueError("MultiIndex tables are unsupported.")
            if parent.tag not in {
                q("office:text"),
                q("office:spreadsheet"),
                q("draw:frame"),
            }:
                raise ValueError("Invalid table slot placement.")
            if self.fmt == "xlsx" and (
                len(frame) > int(slot.get("max-rows", "10000"))
                or len(frame.columns) > int(slot.get("max-columns", "100"))
            ):
                raise ValueError("Table exceeds reserved sheet capacity.")
            # In Calc a slot creates a complete dedicated sheet, avoiding cell overlap.
            table = ET.Element(
                q("table:table"),
                {q("table:name"): slot.get("sheet-name", slot.get("name"))},
            )
            style = self.style(slot, "table-style-name")
            if style:
                table.set(q("table:style-name"), style)
            table_template = slot.get("table-template-name")
            if table_template:
                templates = {
                    e.get(q("table:name"))
                    for e in self.root.iter(q("table:table-template"))
                }
                if self.fmt != "pptx" or table_template not in templates:
                    raise ValueError(
                        "Missing or unsupported presentation table template."
                    )
                table.set(q("table:template-name"), table_template)
                table.set(q("table:use-first-row-styles"), "true")
                table.set(q("table:use-banding-rows-styles"), "true")

            def column_styles(attribute):
                names = slot.get(attribute, "").split()
                if names and len(names) != len(frame.columns):
                    raise ValueError(f"{attribute} must have one style per column.")
                if any(name not in self.styles for name in names):
                    raise ValueError(f"Missing style in {attribute}.")
                return names

            columns = column_styles("column-style-names")
            cells = column_styles("column-cell-style-names")
            alternate = column_styles("alternate-column-cell-style-names")
            for column in range(len(frame.columns)):
                attributes = {q("table:style-name"): columns[column]} if columns else {}
                ET.SubElement(table, q("table:table-column"), attributes)
            rows = [list(frame.columns), *frame.itertuples(index=False, name=None)]
            for i, values in enumerate(rows):
                container = (
                    ET.SubElement(table, q("table:table-header-rows"))
                    if i == 0 and self.fmt == "docx"
                    else table
                )
                row_style = self.style(
                    slot, "header-row-style-name" if i == 0 else "body-row-style-name"
                )
                row = ET.SubElement(
                    container,
                    q("table:table-row"),
                    {q("table:style-name"): row_style} if row_style else {},
                )
                style = self.style(
                    slot, "header-cell-style-name" if i == 0 else "body-cell-style-name"
                )
                paragraph_style = self.style(
                    slot,
                    "header-paragraph-style-name"
                    if i == 0
                    else "body-paragraph-style-name",
                )
                for column, val in enumerate(values):
                    selected_style = style
                    if i > 0:
                        if alternate and i % 2 == 0:
                            selected_style = alternate[column]
                        elif cells:
                            selected_style = cells[column]
                        elif i % 2 == 0:
                            selected_style = (
                                self.style(slot, "alternate-cell-style-name") or style
                            )
                    cell = ET.SubElement(
                        row,
                        q("table:table-cell"),
                        {q("table:style-name"): selected_style}
                        if selected_style
                        else {},
                    )
                    self._cell(cell, val)
                    if paragraph_style:
                        cell.find(q("text:p")).set(
                            q("text:style-name"), paragraph_style
                        )
            return [table]
        if kind in {"image", "animation"}:
            if slot.get("fit", "contain") != "contain":
                raise ValueError("Only contain image fitting is supported.")
            return [self._image(parent, slot, kind, value)]
        raise ValueError(f"Unsupported slot: {kind}")

    def _cell(self, cell, value):
        if value is None or value is pd.NA or value is pd.NaT:
            text = "--" if self.fmt != "xlsx" else ""
        elif isinstance(value, (float, int)) and not isinstance(value, bool):
            if not math.isfinite(value):
                raise ValueError("Nonfinite table numbers are unsupported.")
            if (
                isinstance(value, int)
                and len(str(abs(value))) > 15
                and self.fmt == "xlsx"
            ):
                raise ValueError("Large integer requires explicit string treatment.")
            cell.set(q("office:value-type"), "float")
            cell.set(q("office:value"), str(value))
            text = str(value)
        elif isinstance(value, bool):
            cell.set(q("office:value-type"), "boolean")
            cell.set(q("office:boolean-value"), str(value).lower())
            text = str(value)
        elif isinstance(value, (date, datetime)):
            if isinstance(value, datetime) and value.tzinfo:
                raise ValueError("Timezone-aware dates require explicit normalization.")
            cell.set(q("office:value-type"), "date")
            cell.set(q("office:date-value"), value.isoformat())
            text = value.isoformat()
        else:
            text = str(value)
        if not cell.get(q("office:value-type")):
            cell.set(q("office:value-type"), "string")
        plain(ET.SubElement(cell, q("text:p")), text)

    def _image(self, parent, slot, kind, value):
        if kind == "animation":
            if (
                self.fmt != "pptx"
                or parent.tag != q("draw:page")
                or not isinstance(value, AnimationInput)
            ):
                raise ValueError("Animations require a slide and AnimationInput.")
            if (
                slot.get("start", "automatic") != "automatic"
                or slot.get("loop", "true") != "true"
            ):
                raise ValueError("Only automatic looping GIF playback is supported.")
            path = Path(value.path)
            if path.suffix.lower() != ".gif":
                raise ValueError(
                    "MP4 export requires a separately verified media transport."
                )
            with Image.open(path) as image:
                frames = getattr(image, "n_frames", 1)
                if frames < 2:
                    raise ValueError("Animation is flattened.")
                if frames > 900 or image.width > 1920 or image.height > 1080:
                    raise ValueError("Animation exceeds frame/dimension limits.")
                if frames * image.width * image.height * 4 > 512 * 1024 * 1024:
                    raise ValueError("Decoded animation exceeds 512 MiB.")
                if image.info.get("loop") != 0:
                    raise ValueError("GIF animation must encode continuous looping.")
                duration = 0
                for index in range(frames):
                    image.seek(index)
                    duration += image.info.get("duration", 0)
                if duration <= 0 or duration > 30000:
                    raise ValueError(
                        "Animation must have positive duration <=30 seconds."
                    )
            if path.stat().st_size > 50 * 1024 * 1024:
                raise ValueError("Animation exceeds 50 MiB.")
            self.media_info.append(
                {
                    "input": slot.get("name"),
                    "format": "gif",
                    "frames": frames,
                    "duration_ms": duration,
                    "width": image.width,
                    "height": image.height,
                    "start": "automatic",
                    "loop": True,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
            self.media.append(path.read_bytes())
            if sum(map(len, self.media)) > 100 * 1024 * 1024:
                raise ValueError("Deck animation media exceeds 100 MiB.")
            poster = Path(value.poster_path)
            with Image.open(poster) as image:
                image.verify()
            staged_poster = (
                self.workspace / "report-assets" / f"poster-{len(self.assets)}.png"
            )
            staged_poster.parent.mkdir(exist_ok=True)
            with Image.open(poster) as image:
                image.convert("RGB").save(staged_poster)
            self.assets.append(staged_poster)
        elif isinstance(value, FigureInput):
            path = self.workspace / f"figure-{len(self.assets)}.png"
            from report_agent.rendering.graphs.adapters import MatplotlibFigureExporter

            MatplotlibFigureExporter(format="png").export(value.figure, path)
        else:
            path = Path(value.path)
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".gif"}:
            raise ValueError("Office images require PNG/JPEG; animations require GIF.")
        if kind == "image" and path.suffix.lower() == ".gif":
            raise ValueError("Use animation slots for GIF assets.")
        if path.stat().st_size > 50 * 1024 * 1024:
            raise ValueError("Media exceeds 50 MiB.")
        data = path.read_bytes()
        if len(data) > 50 * 1024 * 1024:
            raise ValueError("Media exceeds 50 MiB limit.")
        with Image.open(path) as image:
            mime_type = Image.MIME[image.format]
            width, height = image.size
            image.verify()
        frame = ET.Element(
            q("draw:frame"),
            {
                q("draw:name"): f"asset-{len(self.assets)}",
                q("svg:width"): dimension(slot.get("width")),
                q("svg:height"): dimension(slot.get("height")),
            },
        )
        if self.fmt == "pptx":
            if parent.tag != q("draw:page"):
                raise ValueError("Slide images require a page parent.")
            for coordinate in ("x", "y"):
                location = slot.get(coordinate, "0cm")
                if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?(?:cm|mm|in|pt)", location):
                    raise ValueError(
                        "Image coordinates require nonnegative physical units."
                    )
                frame.set(q("svg:" + coordinate), location)
        elif parent.tag not in {q("text:p"), q("text:h")}:
            raise ValueError("Writer images require a paragraph parent.")
        else:
            frame.set(q("text:anchor-type"), "as-char")

        # Fit into requested frame without changing the image aspect ratio.
        def cm(v):
            match = re.fullmatch(r"([0-9.]+)(cm|mm|in|pt)", v)
            return (
                float(match[1])
                * {"cm": 1, "mm": 0.1, "in": 2.54, "pt": 2.54 / 72}[match[2]]
            )

        w, h = cm(slot.get("width")), cm(slot.get("height"))
        scale = min(w / width, h / height)
        frame.set(q("svg:width"), f"{width * scale:.6f}cm")
        frame.set(q("svg:height"), f"{height * scale:.6f}cm")
        image = ET.SubElement(
            frame,
            q("draw:image"),
            {q("draw:mime-type"): "image/gif" if kind == "animation" else mime_type},
        )
        ET.SubElement(image, q("office:binary-data")).text = base64.b64encode(
            data
        ).decode()
        retained = (
            self.workspace
            / "report-assets"
            / (hashlib.sha256(data).hexdigest() + path.suffix.lower())
        )
        retained.parent.mkdir(exist_ok=True)
        retained.write_bytes(data)
        self.assets.append(retained)
        return frame
