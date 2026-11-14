"""Immutable accepted bundles; every edit starts a separate draft."""

import re
import shutil
from pathlib import Path
from threading import Lock
from uuid import uuid4

from report_agent.authoring.compiler import compile_template
from report_agent.definitions.loader import load_definition, save_definition
from report_agent.errors import ReportError


class ReportStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self._lock = Lock()

    def draft(self, definition):
        key = f"drafts/{uuid4().hex}"
        directory = self.root / key
        compile_template(definition, directory)
        save_definition(definition, directory / "report.yaml")
        return key

    def path(self, key):
        if not re.fullmatch(
            r"drafts/[a-f0-9]{32}|accepted/[a-z][a-z0-9_-]{0,63}/v[1-9][0-9]*", key
        ):
            raise ReportError(
                "Invalid report reference. Choose a reference from report_context.",
                code="invalid_reference",
            )
        directory = (self.root / key).resolve()
        if (
            not directory.is_relative_to(self.root)
            or not (directory / "report.yaml").is_file()
        ):
            raise ReportError(
                "Report definition not found. Refresh report_context.",
                code="report_not_found",
            )
        return directory

    def load(self, key):
        return load_definition(self.path(key) / "report.yaml")

    def delete_draft(self, key):
        """Delete an explicitly owned temporary draft, never an accepted bundle."""
        if not re.fullmatch(r"drafts/[a-f0-9]{32}", key):
            raise ReportError(
                "Only temporary draft references can be deleted.",
                code="invalid_reference",
            )
        with self._lock:
            if not (self.root / key).exists():
                return
            shutil.rmtree(self.path(key))

    def accept(self, key, sample_path: Path):
        if not key.startswith("drafts/"):
            raise ValueError("Only drafts can be accepted.")
        if not sample_path.is_file():
            raise ValueError("Render and review a successful preview first.")
        directory = self.path(key)
        definition = self.load(key)
        parent = self.root / "accepted" / definition.id
        with self._lock:
            parent.mkdir(parents=True, exist_ok=True)
            versions = [
                int(p.name[1:]) for p in parent.glob("v*") if p.name[1:].isdigit()
            ]
            version = max(versions, default=0) + 1
            destination = parent / f"v{version}"
            staging = parent / f".pending-{uuid4().hex}"
            try:
                shutil.copytree(directory, staging)
                previews = staging / "previews"
                previews.mkdir(exist_ok=True)
                shutil.copy2(sample_path, previews / f"sample{sample_path.suffix}")
                staging.rename(destination)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
        return destination.relative_to(self.root).as_posix()

    def list(self):
        result = []
        for path in sorted((self.root / "accepted").glob("*/v*/report.yaml")):
            definition = load_definition(path)
            result.append(
                {
                    "reference": path.parent.relative_to(self.root).as_posix(),
                    "name": definition.name,
                    "description": definition.description,
                    "format": definition.layout.format,
                }
            )
        return result

    def list_drafts(self):
        result = []
        seen = set()
        for path in sorted(
            (self.root / "drafts").glob("*/report.yaml"),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        ):
            definition = load_definition(path)
            if definition.layout.title.startswith("DEMONSTRATION") or any(
                q.connection == "demonstration" for q in definition.queries.values()
            ):
                continue
            if definition.id in seen:
                continue
            seen.add(definition.id)
            result.append(
                {
                    "reference": path.parent.relative_to(self.root).as_posix(),
                    "name": definition.name,
                    "format": definition.layout.format,
                }
            )
        return result
