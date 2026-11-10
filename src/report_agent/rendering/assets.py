"""Validated asset staging and graphics commands shared by image/graph strategies."""

from hashlib import sha256
from pathlib import Path
from shutil import copyfile

from PIL import Image

from report_agent.models.results import RenderedContent
from report_agent.models.template import RenderContext


def stage_asset(source: Path, context: RenderContext) -> Path:
    source = Path(source).expanduser().resolve(strict=True)
    suffix = source.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".pdf"}:
        raise ValueError("Supported graphics formats are PNG, JPEG, and PDF.")
    if suffix == ".pdf":
        with source.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                raise ValueError("Invalid PDF graphics asset.")
    else:
        with Image.open(source) as image:
            expected = "PNG" if suffix == ".png" else "JPEG"
            if image.format != expected:
                raise ValueError("Image encoding does not match the file extension.")
            image.verify()
    digest = sha256(source.read_bytes()).hexdigest()[:24]
    root = context.document_root or context.workspace
    destination = root / "report-assets" / f"{digest}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source != destination:
        copyfile(source, destination)
    return destination


def graphics_content(
    asset: Path, context: RenderContext, width: str | None
) -> RenderedContent:
    root = context.document_root or context.workspace
    relative = asset.relative_to(root).as_posix()
    dimension = width or r"1\linewidth"
    return RenderedContent(
        latex=rf"\includegraphics[width={dimension}]{{{relative}}}",
        assets=(asset,),
        required_packages=frozenset({"graphicx"}),
    )
