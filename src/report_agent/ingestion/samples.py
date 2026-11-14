"""Extract text, headings, slide/sheet boundaries, and limited design cues."""

import re
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from report_agent.ingestion.archives import validate_members
from report_agent.templates.odf import parse

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_SAMPLE_CHARS = 30000


def extract_sample(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > MAX_UPLOAD_BYTES:
        raise ValueError("Upload a sample no larger than 10 MiB.")
    suffix = path.suffix.lower()
    cues = []
    if suffix in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8")
    elif suffix == ".pdf":
        text, cues = _pdf(path)
    elif suffix in {".docx", ".pptx", ".xlsx"}:
        text, cues = _office(path, suffix)
    else:
        raise ValueError("Upload PDF, DOCX, PPTX, XLSX, TXT or Markdown.")
    text = text.strip()
    if not text:
        raise ValueError("No readable text found. Scanned PDFs need OCR first.")
    if len(text) > MAX_SAMPLE_CHARS:
        raise ValueError("Sample exceeds 30,000 characters; upload an excerpt.")
    return {"name": path.name, "format": suffix[1:], "text": text, "design_cues": cues}


def _pdf(path):
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("Upload an unencrypted PDF.")
        if len(reader.pages) > 30:
            raise ValueError("PDF samples may contain at most 30 pages.")
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
            if sum(map(len, parts)) > MAX_SAMPLE_CHARS:
                raise ValueError("Sample exceeds 30,000 characters.")
        page = reader.pages[0] if reader.pages else None
        cues = [f"Pages: {len(reader.pages)}"]
        if page:
            cues.append(
                f"Page size: {float(page.mediabox.width):.0f} x "
                f"{float(page.mediabox.height):.0f} pt"
            )
        return "\n\n".join(parts), cues
    except PyPdfError as exc:
        raise ValueError("Unreadable PDF sample.") from exc


def _office(path, suffix):
    try:
        with ZipFile(path) as archive:
            validate_members(archive)

            def read(name):
                if archive.getinfo(name).file_size > MAX_UPLOAD_BYTES:
                    raise ValueError("Document XML exceeds 10 MiB.")
                return parse(archive.read(name))

            if suffix == ".docx":
                root = read("word/document.xml")
                word = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
                parts, cues = [], []
                for paragraph in root.iter(word + "p"):
                    text = "".join(n.text or "" for n in paragraph.iter(word + "t"))
                    parts.append(text)
                    style = paragraph.find(f"{word}pPr/{word}pStyle")
                    if style is not None and text:
                        cues.append(f"{style.get(word + 'val')}: {text[:120]}")
                return "\n".join(parts), cues[:50]
            if suffix == ".pptx":
                names = sorted(
                    (
                        n
                        for n in archive.namelist()
                        if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)
                    ),
                    key=lambda n: int(re.search(r"slide(\d+)", n)[1]),
                )
                if len(names) > 50:
                    raise ValueError("Presentation samples support at most 50 slides.")
                drawing = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
                parts = [
                    f"Slide {i + 1}\n"
                    + "\n".join(n.text or "" for n in read(name).iter(drawing + "t"))
                    for i, name in enumerate(names)
                ]
                return "\n\n".join(parts), [f"Slides: {len(names)}"]
            sheet = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
            shared = []
            if "xl/sharedStrings.xml" in archive.namelist():
                shared = [
                    "".join(n.text or "" for n in item.iter(sheet + "t"))
                    for item in read("xl/sharedStrings.xml").iter(sheet + "si")
                ]
            cues = [
                n.get("name", "") for n in read("xl/workbook.xml").iter(sheet + "sheet")
            ]
            parts = []
            for name in sorted(
                n
                for n in archive.namelist()
                if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)
            ):
                parts.append(name)
                for row in read(name).iter(sheet + "row"):
                    cells = []
                    for cell in row:
                        value = cell.find(sheet + "v")
                        text = value.text or "" if value is not None else ""
                        if cell.get("t") == "s":
                            text = shared[int(text)]
                        elif cell.get("t") == "inlineStr":
                            text = "".join(n.text or "" for n in cell.iter(sheet + "t"))
                        cells.append(text)
                    parts.append(" | ".join(cells))
                    if sum(map(len, parts)) > MAX_SAMPLE_CHARS:
                        raise ValueError("Sample exceeds 30,000 characters.")
            return "\n".join(parts), ["Sheets: " + ", ".join(cues)]
    except (BadZipFile, KeyError, IndexError) as exc:
        raise ValueError("Unreadable Office sample.") from exc
