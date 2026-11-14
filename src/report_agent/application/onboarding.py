"""Session-owned proposals with explicit acceptance and parameter confirmation."""

from dataclasses import dataclass, field
from pathlib import Path
from subprocess import SubprocessError
from threading import RLock
from uuid import uuid4

from report_agent.authoring.previews import thumbnails
from report_agent.definitions.models import ReportDefinition


@dataclass
class Onboarding:
    id: str = field(default_factory=lambda: uuid4().hex)
    draft: str | None = None
    accepted: str | None = None
    pending: dict | None = None
    sample: dict | None = None
    preview_reference: str | None = None
    preview_path: Path | None = None
    files: list[str] = field(default_factory=list)
    gallery: list[tuple[str, str]] = field(default_factory=list)
    candidates: dict[str, str] = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)
    source_labels: dict[str, str] = field(default_factory=dict)
    display_events: list[dict] = field(default_factory=list)
    lock: RLock = field(default_factory=RLock)


class OnboardingService:
    def __init__(self, store, runs):
        self.store, self.runs = store, runs

    def stage(self, session, data):
        definition = ReportDefinition.model_validate(data)
        session.draft = self.store.draft(definition)
        session.preview_reference = session.preview_path = None
        session.pending = None
        session.files.clear()
        session.gallery.clear()
        return session.draft

    def preview(self, session, reference, parameters, sample_tables=None):
        if reference == session.draft:
            session.preview_reference = session.preview_path = None
        result = self.runs.run(reference, parameters, sample_tables=sample_tables)
        if result.output_path is None:
            return {
                "success": False,
                "diagnostics": [d.__dict__ for d in result.diagnostics],
            }
        session.files.append(str(result.output_path))
        if reference == session.draft:
            session.preview_reference, session.preview_path = (
                reference,
                result.output_path,
            )
        warning = None
        try:
            session.gallery.extend(
                (str(p), self.store.load(reference).name) for p in thumbnails(result)
            )
        except (ValueError, OSError, SubprocessError) as exc:
            warning = f"Report rendered; thumbnail failed ({type(exc).__name__})."
        return {
            "success": True,
            "report": reference,
            "thumbnail_warning": warning,
            "diagnostics": [d.__dict__ for d in result.diagnostics],
        }

    def accept(self, session):
        if (
            not session.draft
            or session.preview_reference != session.draft
            or not session.preview_path
        ):
            raise ValueError(
                "Preview the current draft successfully before accepting it."
            )
        reference = self.store.accept(session.draft, session.preview_path)
        session.accepted, session.draft, session.pending = reference, None, None
        return reference

    def propose(self, session, reference, parameters):
        if not reference.startswith("accepted/"):
            raise ValueError("Accept the template before starting repeat runs.")
        definition, values, _ = self.runs.prepare(reference, parameters)
        session.pending = {"reference": reference, "parameters": values}
        return {"report": definition.name, **session.pending}

    def confirm(self, session):
        if session.pending is None:
            raise ValueError("Ask the agent to prepare a report run first.")
        pending = session.pending
        result = self.runs.run(pending["reference"], pending["parameters"])
        if result.output_path:
            session.pending = None
            session.files = [str(result.output_path)]
            session.gallery.clear()
            try:
                session.gallery = [
                    (str(path), self.store.load(pending["reference"]).name)
                    for path in thumbnails(result)
                ]
            except (ValueError, OSError, SubprocessError):
                # A successful report remains downloadable without image previews.
                pass
        return result
