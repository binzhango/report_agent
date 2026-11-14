"""Optional visual previews derived from the actual engine output."""

import shutil
import subprocess
from pathlib import Path

from report_agent.compilation.libreoffice import LibreOfficeConverter


def thumbnails(result):
    if not result.output_path or not shutil.which("pdftoppm"):
        return []
    output = result.output_path
    if output.suffix == ".pdf":
        pdf = output
    else:
        expanded = next(
            (p for p in result.artifacts if p.suffix in {".fodt", ".fods", ".fodp"}),
            None,
        )
        if expanded is None:
            return []
        pdf = LibreOfficeConverter().convert(expanded, "pdf", output.parent / "preview")
    prefix = output.parent / "page"
    subprocess.run(
        [
            "pdftoppm",
            "-f",
            "1",
            "-l",
            "12",
            "-scale-to",
            "1000",
            "-png",
            str(pdf),
            str(prefix),
        ],
        capture_output=True,
        check=True,
        timeout=60,
    )
    return sorted(Path(output.parent).glob("page-*.png"))
