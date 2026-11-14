"""Flat ODF to Office orchestration with retained diagnostics and atomic publication."""

import hashlib
import json
import logging
import posixpath
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from PIL import Image

from report_agent.compilation.libreoffice import ConversionError, LibreOfficeConverter
from report_agent.models.inputs import (
    AnimationInput,
    FigureInput,
    GraphInput,
    ImageInput,
    TableInput,
    TextInput,
)
from report_agent.models.results import Diagnostic, RenderResult
from report_agent.storage.artifacts import LocalArtifactStore, publish_snapshot
from report_agent.storage.workspace import TemporaryWorkspaceManager
from report_agent.templates.odf import OdfTemplate, parse
from report_agent.validation.text import text_issues

logger = logging.getLogger(__name__)


def verify_package(path, fmt, animations=()):
    main = {
        "docx": "word/document.xml",
        "xlsx": "xl/workbook.xml",
        "pptx": "ppt/presentation.xml",
    }[fmt]
    try:
        with ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ValueError("Corrupt Office archive.")
            names = set(archive.namelist())
            for part in (main, "[Content_Types].xml", "_rels/.rels"):
                parse(archive.read(part))
            relationships = {}
            for name in names:
                if name.endswith(".rels"):
                    rels = parse(archive.read(name))
                    base = posixpath.dirname(posixpath.dirname(name))
                    source_part = posixpath.join(base, posixpath.basename(name)[:-5])
                    for rel in rels:
                        if rel.get("TargetMode") == "External":
                            raise ValueError(
                                "External package relationship is unsupported."
                            )
                        target = rel.get("Target", "")
                        resolved = (
                            posixpath.normpath(posixpath.join(base, target))
                            if not target.startswith("/")
                            else target[1:]
                        )
                        relationships.setdefault(source_part, set()).add(resolved)
                        if resolved not in names:
                            raise ValueError(f"Missing relationship target: {resolved}")
            # Follow layout/master relationships as well as slide-local media.
            # Unreferenced media files cannot satisfy animation preservation.
            reachable = set()
            pending = [main]
            while pending:
                part = pending.pop()
                if part not in reachable:
                    reachable.add(part)
                    pending.extend(relationships.get(part, ()))
            media = [archive.read(n) for n in reachable if n.startswith("ppt/media/")]
            for source in animations:
                digest = hashlib.sha256(source).digest()
                matches = [m for m in media if hashlib.sha256(m).digest() == digest]
                if not matches:
                    raise ConversionError(
                        "animation_not_preserved",
                        "Export did not preserve original animated GIF bytes.",
                    )
                with Image.open(BytesIO(matches[0])) as image:
                    if getattr(image, "n_frames", 1) < 2:
                        raise ValueError("Flattened animation.")
    except (BadZipFile, KeyError) as exc:
        raise ConversionError("invalid_office_package", str(exc)) from exc


class LibreOfficeBackend:
    def __init__(self, *, workspaces=None, artifacts=None, converter=None):
        self.workspaces = workspaces or TemporaryWorkspaceManager()
        self.artifacts = artifacts or LocalArtifactStore()
        self.converter = converter or LibreOfficeConverter()

    def render(self, request, metadata):
        stage = "template_loading"
        retained = []
        retention_issues = []
        try:
            selected = request.template.expanduser().absolute()
            root = selected if selected.is_dir() else selected.parent
            relative = Path(metadata.entrypoint)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Entrypoint must stay inside template root.")
            source = root / relative
            if not selected.is_dir() and selected != source:
                raise ValueError("Selected template does not match entrypoint.")
            resources = []
            for path in root.rglob("*"):
                if any(
                    part.startswith(".") or part.endswith(".artifacts")
                    for part in path.relative_to(root).parts
                ):
                    continue
                if path.is_symlink():
                    raise ValueError("Template symlinks are unsupported.")
                if path.is_file():
                    resources.append(path)
            if source not in resources or not source.resolve().is_relative_to(
                root.resolve()
            ):
                raise ValueError("Missing template entrypoint.")
            stage = "output_validation"
            output = request.output.expanduser().absolute()
            fmt = metadata.document.format
            if output.suffix.lower() != f".{fmt}":
                raise ValueError("Output suffix does not match metadata format.")
            destination = output.parent / f"{output.stem}.artifacts"
            protected = {p.resolve() for p in resources}
            if output.resolve() in protected or any(
                p.resolve().is_relative_to(destination.resolve()) for p in resources
            ):
                raise ValueError("Output/artifacts would overwrite template resources.")
            stage = "input_validation"
            template = OdfTemplate(source.read_text(), fmt)
            issues = self._validate(template, request.inputs, metadata)
            if issues:
                return RenderResult(diagnostics=tuple(issues))
            with self.workspaces.create() as workspace:
                try:
                    stage = "content_rendering"
                    text = template.expand(request.inputs, metadata.inputs, workspace)
                    expanded = workspace / "expanded"
                    expanded = expanded.with_suffix(source.suffix)
                    expanded.write_text(text)
                    stage = "conversion"
                    candidate = self.converter.convert(
                        expanded, fmt, workspace / "export"
                    )
                    stage = "output_validation"
                    verify_package(candidate, fmt, template.media)
                    manifest = workspace / "build.json"
                    manifest.write_text(
                        json.dumps(
                            {
                                "engine": "libreoffice",
                                "version": (
                                    workspace / "export/version.txt"
                                ).read_text()
                                if (workspace / "export/version.txt").exists()
                                else "unknown",
                                "format": fmt,
                                "experimental": True,
                                "playback_verified": False,
                                "source_sha256": hashlib.sha256(
                                    text.encode()
                                ).hexdigest(),
                                "animations": template.media_info,
                                "generators": {
                                    name: d.generator
                                    for name, d in metadata.inputs.items()
                                    if d.source == "generator"
                                },
                            },
                            indent=2,
                        )
                    )
                    stage = "publication"
                    assets = [
                        expanded,
                        manifest,
                        *[p for p in (workspace / "export").glob("*.log")],
                        *[p for p in (workspace / "export").glob("version.txt")],
                        *[p for p in (workspace / "report-assets").glob("*")],
                    ]
                    if any(
                        (destination / p.relative_to(workspace)).resolve() in protected
                        for p in assets
                    ):
                        raise ValueError(
                            "Artifact destination would overwrite template resources."
                        )
                    retained = publish_snapshot(
                        self.artifacts,
                        [(p, p.relative_to(workspace)) for p in assets],
                        destination,
                        protected,
                    )
                    final = self.artifacts.publish(candidate, output)
                    return RenderResult(
                        diagnostics=(
                            Diagnostic(
                                "compatibility",
                                "experimental_backend",
                                "Office compatibility and playback need review.",
                                severity="warning",
                            ),
                        ),
                        artifacts=tuple(retained),
                        output_path=final,
                        output_format=fmt,
                    )
                except Exception:
                    # Retain source/logs on failure without publishing the candidate.
                    failure_assets = [
                        *workspace.glob("expanded.*"),
                        *(workspace / "export").glob("*.log"),
                    ]
                    try:
                        retained = publish_snapshot(
                            self.artifacts,
                            [(p, p.relative_to(workspace)) for p in failure_assets],
                            destination,
                            protected,
                        )
                    except Exception as retention_error:
                        retention_issues.append(
                            Diagnostic(
                                "publication",
                                "artifact_retention_failed",
                                str(retention_error),
                                severity="warning",
                            )
                        )
                    raise
        except (ValueError, OSError) as exc:
            return RenderResult(
                diagnostics=(
                    Diagnostic(stage, getattr(exc, "code", "invalid_input"), str(exc)),
                )
                + tuple(retention_issues),
                artifacts=tuple(retained),
            )
        except Exception as exc:
            logger.exception("Unexpected Office render failure during %s", stage)
            return RenderResult(
                diagnostics=(
                    Diagnostic(stage, "internal_error", f"{type(exc).__name__}: {exc}"),
                )
                + tuple(retention_issues),
                artifacts=tuple(retained),
            )

    @staticmethod
    def _validate(template, inputs, metadata):
        issues = []

        def issue(code, message, name):
            issues.append(
                Diagnostic("input_validation", code, message, input_name=name)
            )

        slots = template.slots()
        names = {n for n, _ in slots}
        types = {
            "text": (TextInput,),
            "table": (TableInput,),
            "image": (ImageInput,),
            "graph": (GraphInput, FigureInput),
            "animation": (AnimationInput,),
        }
        slot_types = {
            "text": {"text"},
            "paragraphs": {"text"},
            "cell": {"text"},
            "table": {"table"},
            "image": {"image", "graph"},
            "animation": {"animation"},
        }
        for n in names - metadata.inputs.keys():
            issue("undeclared_placeholder", "Unknown template input.", n)
        for n in inputs.keys() - metadata.inputs.keys():
            issue("unknown_input", "Unknown runtime input.", n)
        for n, d in metadata.inputs.items():
            if d.visible and n not in names:
                issue("unused_input", "No template slot.", n)
            if not d.visible and n in names:
                issue("hidden_placeholder", "Hidden input in template.", n)
            if n not in inputs and d.required and d.default is None:
                issue("missing_input", "Missing required input.", n)
            if n not in inputs and d.default is not None:
                for code, message in text_issues(TextInput(d.default), d):
                    issue(code, message, n)
            if n in inputs:
                if not isinstance(inputs[n], types[d.type]):
                    issue("input_type", f"Expected {d.type} input.", n)
                elif isinstance(inputs[n], TextInput):
                    for code, message in text_issues(inputs[n], d):
                        issue(code, message, n)
        for n, kind in slots:
            if n in metadata.inputs and metadata.inputs[n].type not in slot_types.get(
                kind, set()
            ):
                issue("invalid_slot", f"Incompatible slot {kind}.", n)
        return issues
