"""Benchmark real report builds; no mocks or cached PDFs."""

# Configure writable plotting caches before importing graphics libraries.
# ruff: noqa: E402

import argparse
import json
import os
import platform
import runpy
import shutil
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "output/matplotlib-cache"))
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / "output/cache"))

import matplotlib as mpl

from report_agent import RenderRequest, TextInput, create_renderer
from report_agent.models.inputs import ContentInput

type InputFactory = Callable[[Path], dict[str, ContentInput]]


def plain_inputs(_: Path) -> dict[str, ContentInput]:
    return {
        "title": TextInput("Quarterly business review"),
        "summary": TextInput(
            "Revenue increased by 12% to $1,250,000.\n\n"
            "The team will focus on customer retention next quarter."
        ),
    }


def summary(values: list[float]) -> dict[str, float]:
    return {"median": median(values), "min": min(values), "max": max(values)}


def benchmark(name: str, bundle: Path, prepare: InputFactory, runs: int) -> dict:
    samples = []
    with TemporaryDirectory(prefix="report-benchmark-") as temporary:
        root = Path(temporary)
        for index in range(runs + 1):
            run_root = root / str(index)
            started = perf_counter()
            inputs = prepare(run_root / "assets")
            prepared = perf_counter()
            result = create_renderer().render(
                RenderRequest(
                    template=bundle,
                    metadata=bundle / "template.json",
                    inputs=inputs,
                    output=run_root / "report.pdf",
                )
            )
            finished = perf_counter()
            if result.pdf_path is None:
                raise RuntimeError(f"Benchmark build failed: {result.diagnostics}")
            if any(item.severity == "error" for item in result.diagnostics):
                raise RuntimeError(f"Benchmark build had errors: {result.diagnostics}")
            samples.append(
                {
                    "preparation_seconds": prepared - started,
                    "render_seconds": finished - prepared,
                    "total_seconds": finished - started,
                    "pdf_bytes": result.pdf_path.stat().st_size,
                    "warnings": len(result.diagnostics),
                }
            )
        pages = None
        if shutil.which("pdfinfo"):
            information = subprocess.check_output(
                ["pdfinfo", str(result.pdf_path)], text=True
            )
            pages = int(
                next(
                    line.split(":", 1)[1]
                    for line in information.splitlines()
                    if line.startswith("Pages:")
                )
            )
    return {
        "name": name,
        "pages": pages,
        "runs_after_first": runs,
        "first_request": samples[0],
        "subsequent_requests": {
            metric: summary([item[metric] for item in samples[1:]])
            for metric in ("preparation_seconds", "render_seconds", "total_seconds")
        },
        "samples": samples,
    }


def hardware(key: str) -> str | None:
    if platform.system() != "Darwin":
        return None
    try:
        return subprocess.check_output(
            ["sysctl", "-n", key], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runs",
        type=int,
        default=10,
        help="Measured requests after one separately recorded first request.",
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "output/benchmarks/report-generation.json"
    )
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    example = runpy.run_path(str(ROOT / "examples/comprehensive/render.py"))
    with mpl.rc_context(
        {"font.family": "DejaVu Sans", "font.size": 10, "pdf.fonttype": 42}
    ):
        cases = [
            benchmark(
                "Plain text", ROOT / "examples/plain_text", plain_inputs, args.runs
            ),
            benchmark(
                "Comprehensive",
                ROOT / "examples/comprehensive",
                example["build_inputs"],
                args.runs,
            ),
        ]
    report = {
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "environment": {
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "cpu": hardware("machdep.cpu.brand_string"),
            "memory_bytes": hardware("hw.memsize"),
            "python": platform.python_version(),
            "packages": {
                name: version(name) for name in ["pandas", "matplotlib", "jinja2"]
            },
            "compiler": subprocess.check_output(
                ["texres", "--version"], text=True
            ).strip(),
        },
        "methodology": {
            "clock": "perf_counter wall time",
            "concurrency": 1,
            "scope": (
                "Preparation regenerates all runtime inputs and upstream assets; "
                "rendering includes validation, staging, content adapters, TeX "
                "compilation, artifact publication, and workspace cleanup."
            ),
            "excluded": (
                "Python startup/imports, database queries, LLM calls, "
                "pdfinfo measurement, and benchmark JSON writing."
            ),
            "cache": (
                "Fresh per-render TeX workspace/cache and no PDF reuse. "
                "OS/font caches remain warm. First requests are not true "
                "machine-cold measurements."
            ),
        },
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for case in cases:
        render = case["subsequent_requests"]["render_seconds"]
        total = case["subsequent_requests"]["total_seconds"]
        print(
            f"{case['name']} ({case['pages']} pages): "
            f"render median {render['median']:.3f}s, "
            f"range {render['min']:.3f}-{render['max']:.3f}s; "
            f"including preparation {total['median']:.3f}s"
        )
    print(f"Raw results: {args.output}")


if __name__ == "__main__":
    main()
