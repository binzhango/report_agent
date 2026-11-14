"""Session-owned proposals with explicit acceptance and parameter confirmation."""

from dataclasses import dataclass, field
from pathlib import Path
from subprocess import SubprocessError
from threading import Lock, RLock
from uuid import uuid4

from report_agent.authoring.previews import thumbnails
from report_agent.definitions.bindings import bind_queries
from report_agent.definitions.calendar_months import expand_report_month
from report_agent.definitions.models import ReportDefinition
from report_agent.errors import ReportError


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
    example_drafts: set[str] = field(default_factory=set)
    preview_queries: dict = field(default_factory=dict)
    input_form: dict | None = None
    form_answers: dict[str, dict] = field(default_factory=dict)
    accepted_previews: dict[str, dict] = field(default_factory=dict)
    repair_attempts: int = 0
    repair_pending: bool = False
    tool_lock: Lock = field(default_factory=Lock)
    lock: RLock = field(default_factory=RLock)

    def begin_turn(self):
        self.repair_attempts = 0
        self.repair_pending = False


class OnboardingService:
    def __init__(self, store, runs):
        self.store, self.runs = store, runs

    def discard_examples(self, session, *, keep=None):
        for reference in session.example_drafts.copy():
            if reference != keep:
                self.store.delete_draft(reference)
                session.example_drafts.remove(reference)
                if session.draft == reference:
                    session.draft = None
                    session.preview_reference = session.preview_path = None
                    session.preview_queries = {}
        session.candidates = {
            name: reference
            for name, reference in session.candidates.items()
            if reference in session.example_drafts
        }

    def stage(self, session, data):
        definition = ReportDefinition.model_validate(data)
        session.draft = self.store.draft(definition)
        self.discard_examples(session)
        session.preview_reference = session.preview_path = None
        session.preview_queries = {}
        session.pending = None
        session.files.clear()
        session.gallery.clear()
        return session.draft

    def preview(self, session, reference, parameters, sample_tables=None):
        definition = self.store.load(reference)
        if sample_tables is not None and any(
            query.connection != "demonstration" for query in definition.queries.values()
        ):
            raise ReportError(
                "Demonstration rows cannot replace configured data. "
                "Repair the source or query and preview actual data.",
                code="demo_substitution_blocked",
            )
        values, _ = bind_queries(definition, parameters)
        if reference == session.draft:
            session.preview_reference = session.preview_path = None
            session.preview_queries = {}
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
            session.preview_queries = {
                "queries": {
                    name: query.model_dump(mode="json")
                    for name, query in definition.queries.items()
                },
                "parameters": values,
                "source_labels": {
                    query.connection: session.source_labels.get(
                        query.connection, query.connection
                    )
                    for query in definition.queries.values()
                },
                "source_types": {
                    name: type(adapter).__name__
                    for name, adapter in self.runs.sources.items()
                    if name
                    in {query.connection for query in definition.queries.values()}
                },
                "source_filters": {
                    name: adapter.filters
                    for name, adapter in self.runs.sources.items()
                    if name
                    in {query.connection for query in definition.queries.values()}
                    and hasattr(adapter, "filters")
                },
            }
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

    def accept(self, session, *, queries_reviewed=False):
        if (
            not session.draft
            or session.preview_reference != session.draft
            or not session.preview_path
        ):
            raise ReportError(
                "Preview the current draft successfully before accepting it.",
                code="preview_required",
            )
        definition = self.store.load(session.draft)
        if any(
            query.connection == "demonstration" for query in definition.queries.values()
        ):
            raise ReportError(
                "Replace demonstration data with confirmed bindings before acceptance.",
                code="demo_acceptance_blocked",
            )
        if definition.queries and not queries_reviewed:
            raise ReportError(
                "Review the queries and data bindings before accepting this template.",
                code="query_review_required",
            )
        reference = self.store.accept(session.draft, session.preview_path)
        session.accepted_previews[str(session.preview_path)] = {
            "draft": session.draft,
            "reference": reference,
            "name": definition.name,
            "queries_reviewed": bool(definition.queries),
        }
        session.accepted, session.draft, session.pending = reference, None, None
        return reference

    def propose(self, session, reference, parameters, *, report_month=None):
        session.pending = None
        self.store.path(reference)
        if not reference.startswith("accepted/"):
            raise ReportError(
                "Accept the template before starting repeat runs.",
                code="acceptance_required",
            )
        if report_month is not None:
            parameters = expand_report_month(
                self.store.load(reference), parameters, report_month
            )
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
