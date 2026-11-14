"""Agent tools delegate to validated application services."""

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

from report_agent.agent.catalog import catalog_context
from report_agent.agent.errors import public_tool_error
from report_agent.application.input_forms import InputForm, parameter_form
from report_agent.definitions.models import ReportDefinition
from report_agent.errors import ReportError
from report_agent.resolution.models import QuerySource


def build_tools(session, onboarding, sources):
    store = onboarding.store

    def attempt(fn, *, repair=False):
        # ToolNode may execute parallel calls. This lock is separate from the
        # turn lock held by the conversation worker, so tool threads cannot deadlock.
        with session.tool_lock:
            if repair and session.input_form:
                return public_tool_error(
                    ReportError(
                        "Wait for the user to submit the current input form.",
                        code="input_required",
                    )
                )
            if repair and session.repair_pending:
                if session.repair_attempts >= 2:
                    return public_tool_error(
                        ReportError(
                            "Two repair attempts were used this turn. Explain the "
                            "blocker and ask the user for the next input.",
                            code="repair_limit",
                        )
                    )
                session.repair_attempts += 1
            try:
                result = fn()
            except Exception as exc:
                if repair:
                    session.repair_pending = True
                return public_tool_error(exc)
            if repair:
                session.repair_pending = isinstance(result, dict) and (
                    result.get("success") is False or "error" in result
                )
            return result

    def preview(reference, parameters, sample_tables):
        result = onboarding.preview(session, reference, parameters, sample_tables)
        # Renderer diagnostics can contain exception text and local paths. Keep
        # machine-readable repair codes; full details remain in local run artifacts.
        return {
            **result,
            "diagnostics": [
                {key: item[key] for key in ("stage", "code", "severity") if key in item}
                for item in result.get("diagnostics", [])
            ],
        }

    @tool
    def report_context() -> dict:
        """Inspect current draft, uploaded sample, data sources, and saved reports."""
        return {
            "today": datetime.now(
                ZoneInfo(os.environ.get("REPORT_AGENT_TIMEZONE", "America/New_York"))
            )
            .date()
            .isoformat(),
            "sample": session.sample,
            "draft": session.draft,
            "accepted": session.accepted,
            "saved_reports": store.list(),
            "draft_reports": store.list_drafts(),
            "sources": list(sources),
            "source_labels": session.source_labels,
            "candidates": session.candidates,
            "pending": session.pending,
            "input_form": session.input_form,
            "form_answers": session.form_answers,
        }

    @tool
    def request_report_inputs(
        title: str,
        fields: list[dict] | None = None,
        description: str = "",
        report_reference: str | None = None,
        known_parameters: dict | None = None,
    ) -> dict:
        """Ask questions using an interactive form inside the chat, then wait.

        Each field has id, label, type (text, multiline, date, month, integer,
        number, select, boolean), required, default, placeholder, help, choices,
        and allow_other (select only). Use multiline for open questions; select
        with allow_other for an Other text answer. Month accepts November 2026.
        Ask only missing questions; keep the first discovery form to two fields.
        For an accepted report pass report_reference and known_parameters instead
        of fields: the application builds typed inputs from its saved schema.
        Submitting saved report parameters prepares confirmation without a model
        call. Call this tool on its own; it ends the turn to wait for the user.
        """

        def request():
            if report_reference:
                store.path(report_reference)
                if not report_reference.startswith("accepted/"):
                    raise ReportError(
                        "Use an accepted report for a runtime parameter form."
                    )
                form = parameter_form(
                    store.load(report_reference),
                    report_reference,
                    known_parameters or {},
                    title=title,
                    description=description,
                )
            else:
                form = InputForm(
                    title=title, description=description, fields=fields or []
                )
            session.input_form = form.model_dump(mode="json")
            session.pending = None
            return {"status": "awaiting_input", "form": session.input_form}

        return attempt(request, repair=True)

    @tool
    def report_contract() -> dict:
        """Get the definition schema before creating a report or changing bindings."""
        return ReportDefinition.model_json_schema()

    @tool
    def inspect_report(reference: str) -> dict:
        """Read a report layout, bindings, and parameter requirements."""
        return attempt(lambda: store.load(reference).model_dump(mode="json"))

    @tool
    def resume_report_draft(reference: str) -> dict:
        """Resume a previously saved draft after reconnecting. Render a fresh preview
        before acceptance; this never accepts the template on the user's behalf.
        """

        def resume():
            if not reference.startswith("drafts/"):
                raise ReportError(
                    "Use a draft reference, or run an accepted template.",
                    code="draft_required",
                )
            definition = store.load(reference)
            onboarding.discard_examples(session, keep=reference)
            session.draft = reference
            session.preview_reference = session.preview_path = None
            session.preview_queries = {}
            session.pending = None
            session.files.clear()
            session.gallery.clear()
            return definition.model_dump(mode="json")

        return attempt(resume)

    @tool
    def create_draft(definition: dict) -> dict:
        """Validate a complete ReportDefinition and create a new editable draft version.

        Use report_contract for the schema. Fixed text lives in layout.blocks[].text.
        Table blocks need query bindings. This never accepts or publishes a template.
        """
        return attempt(
            lambda: {"draft": onboarding.stage(session, definition)}, repair=True
        )

    @tool
    def preview_report(
        reference: str, parameters: dict, sample_tables: dict | None = None
    ) -> dict:
        """Render a report preview. sample_tables supplies explicitly labeled demo rows.

        With sample_tables omitted, fetch actual data through configured connectors.
        Show previews to the user before suggesting the Accept template button.
        """
        return attempt(
            lambda: preview(reference, parameters, sample_tables), repair=True
        )

    @tool
    def rendered_examples(output_format: str, topic: str) -> list[dict]:
        """Render three labeled demonstration reports so a user can choose a design.

        output_format is pdf, docx, pptx, or xlsx. These examples use synthetic text;
        they are not final content and cannot be accepted until made into a draft.
        """
        results = []
        onboarding.discard_examples(session)
        session.files.clear()
        session.gallery.clear()
        session.candidates.clear()
        for preset in catalog_context():

            def generate(preset=preset):
                rows = preset["demo_rows"]
                definition = ReportDefinition.model_validate(
                    {
                        "id": preset["id"],
                        "name": preset["name"],
                        "description": preset["description"],
                        "layout": {
                            "title": f"DEMONSTRATION — {topic}"[:200],
                            "format": output_format,
                            "accent": preset["color"],
                            "blocks": [
                                {
                                    "name": f"section_{i}",
                                    "heading": heading,
                                    "kind": "table" if i == 1 else "text",
                                    "text": ""
                                    if i == 1
                                    else (
                                        "Illustrative content only. This section "
                                        f"presents {heading.lower()} for the report's "
                                        "audience. Choose this structure, then use "
                                        "your own content and connected data."
                                    ),
                                }
                                for i, heading in enumerate(preset["outline"])
                            ],
                        },
                        "queries": {
                            "section_1": {
                                "connection": "demonstration",
                                "query": "example",
                                "columns": list(rows[0]),
                            }
                        },
                    }
                )
                reference = store.draft(definition)
                session.example_drafts.add(reference)
                session.candidates[preset["name"]] = reference
                return {
                    "name": preset["name"],
                    "description": preset["description"],
                    **preview(reference, {}, {"section_1": rows}),
                }

            results.append(attempt(generate, repair=True))
        return results

    @tool
    def inspect_source(connection: str) -> dict:
        """Inspect a configured source's type, table/sheet names, and column schema."""
        from report_agent.connectors.registry import describe_source

        return attempt(lambda: describe_source(sources[connection]))

    @tool
    def preview_data(
        connection: str,
        query: str,
        params: dict,
        row_limit: int = 1000,
        filters: dict | None = None,
    ) -> dict:
        """Fetch data during onboarding and show columns and the first five rows.

        For a file source use query=data or an Excel sheet name. For HTTP use a
        configured endpoint name. SQL uses bound named parameters such as :start_date.
        """

        def fetch():
            if not 1 <= row_limit <= 100000:
                raise ReportError("Preview row_limit must be between 1 and 100000.")
            source = QuerySource(
                connection=connection, query=query, params=params, row_limit=row_limit
            )
            adapter = sources[connection]
            if filters:
                from report_agent.connectors.files import FileSource
                from report_agent.definitions.models import FileFilter

                if not isinstance(adapter, FileSource):
                    raise ReportError("Column filters require a file source.")
                adapter = FileSource(
                    adapter.path,
                    filters={
                        key: FileFilter.model_validate(value).model_dump()
                        for key, value in filters.items()
                    },
                )
            frame = adapter.fetch(source)
            if frame.empty or len(frame) > row_limit:
                raise ReportError("Data must be nonempty and within the row limit.")
            return {
                "rows": len(frame),
                "columns": {str(k): str(v) for k, v in frame.dtypes.items()},
                "preview": json.loads(
                    frame.head(5).to_json(orient="records", date_format="iso")
                ),
            }

        return attempt(fetch, repair=True)

    @tool
    def propose_report_run(reference: str, parameters: dict) -> dict:
        """Validate parameters for an accepted report and present them for confirmation.

        This does not fetch or render. The user presses Confirm parameters and render;
        then application code executes the saved bindings without another model call.
        """
        return attempt(
            lambda: onboarding.propose(session, reference, parameters), repair=True
        )

    return [
        report_context,
        request_report_inputs,
        report_contract,
        inspect_report,
        resume_report_draft,
        create_draft,
        preview_report,
        rendered_examples,
        inspect_source,
        preview_data,
        propose_report_run,
    ]
