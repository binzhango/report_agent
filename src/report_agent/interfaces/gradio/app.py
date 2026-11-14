"""Conversation and review workspace with state-aware acceptance controls."""

import logging
from pathlib import Path
from queue import Queue
from threading import Thread

from report_agent.application.input_forms import InputForm, parameter_form
from report_agent.errors import ReportError
from report_agent.interfaces.gradio.input_forms import render_input_form
from report_agent.interfaces.gradio.report_review import data_review_html
from report_agent.interfaces.gradio.safe_text import chat_html, plain_text_html
from report_agent.interfaces.gradio.transcript import snapshot

logger = logging.getLogger(__name__)


def request_error(exc):
    """Give actionable guidance without returning provider bodies or credentials."""
    detail = str(exc).lower()
    if type(exc).__name__ == "GraphRecursionError":
        return (
            "The agent reached its step limit before finishing. "
            "Your files and draft are kept. Ask it to continue with the current draft."
        )
    if type(exc).__name__ == "EmptyModelResponse":
        return (
            "The model returned an empty answer. Check its context and output "
            "limits in LM Studio, then retry. Any completed preview is still available."
        )
    if any(
        word in detail
        for word in ("context length", "context window", "n_ctx", "context size")
    ):
        return (
            "The model ran out of context. In LM Studio, reload it with a "
            "context length of at least 32768, then start a new conversation."
        )
    if type(exc).__name__ in {"APIConnectionError", "APITimeoutError"}:
        return (
            "Cannot reach the model. Check that LM Studio's server is running"
            " and a model is loaded, then retry."
        )
    return (
        f"The request could not finish ({type(exc).__name__}). "
        "Your work is kept. Try again; details are in the server log."
    )


def create_app(service):
    import gradio as gr

    kit = Path("examples/conversations").resolve()

    def get_session(key):
        if key is not None:
            try:
                return key, service.get_session(key)
            except KeyError:
                pass
        key = service.new_session()
        return key, service.get_session(key)

    def view(key, status="", *, busy=False, user_message=None):
        key, session = get_session(key)
        events = snapshot(session, status, busy=busy)
        if user_message:
            events.insert(
                max(0, len(events) - 1),
                {
                    "id": "pending-message",
                    "kind": "message",
                    "role": "user",
                    "content": user_message,
                },
            )
        return (
            key,
            events,
            plain_text_html(status) if status else "",
            gr.update(interactive=not busy),
        )

    def run_chat(message, key, *, display_message=None):
        key, _ = get_session(key)
        if not message.strip():
            yield (*view(key, "Write a message to get started."), message)
            return
        yield (
            *view(
                key,
                "Working on your report…",
                busy=True,
                user_message=display_message or message,
            ),
            "",
        )
        updates = Queue()

        def work():
            try:
                service.send(
                    key,
                    message,
                    display_message=display_message,
                    progress=lambda label: updates.put(
                        (*view(key, label, busy=True), gr.skip())
                    ),
                )
                updates.put((*view(key), gr.skip()))
            except Exception as exc:
                logger.exception("Report conversation failed")
                updates.put((*view(key, request_error(exc)), gr.skip()))
            finally:
                updates.put(None)

        Thread(target=work, daemon=True).start()
        while (update := updates.get()) is not None:
            yield update

    def chat(message, key):
        yield from run_chat(message, key)

    def start_discovery(key):
        key, session = get_session(key)
        with session.lock:
            session.pending = None
            session.input_form = InputForm(
                title="Let's shape your report",
                description="Start with the purpose and audience. "
                "We’ll choose the format next.",
                fields=[
                    {
                        "id": "purpose",
                        "label": "What should this report help you decide?",
                        "type": "multiline",
                    },
                    {"id": "audience", "label": "Who will read it?", "type": "text"},
                ],
            ).model_dump(mode="json")
            session.history.extend(
                [
                    {"role": "user", "content": "Help me get started."},
                    {
                        "role": "assistant",
                        "content": "Tell me the purpose and audience "
                        "in the form below.",
                    },
                ]
            )
        return view(key)

    def submit_inputs(key, form_id, answers):
        try:
            result = service.submit_inputs(key, form_id, answers)
        except ReportError as exc:
            yield *[gr.skip() for _ in range(4)], plain_text_html(str(exc))
            return
        except Exception as exc:
            logger.exception("Input form submission failed")
            yield *[gr.skip() for _ in range(4)], plain_text_html(request_error(exc))
            return
        if result["report_run"]:
            session = service.get_session(key)
            session.history.extend(
                [
                    {"role": "user", "content": result["summary"]},
                    {
                        "role": "assistant",
                        "content": "Your inputs are ready. Confirm the parameters "
                        "below to render your report.",
                    },
                ]
            )
            yield *view(key), ""
            return
        for update in run_chat(
            result["message"], key, display_message=result["summary"]
        ):
            yield *update[:4], ""

    def sample_upload(path, key):
        key, _ = get_session(key)
        if not path:
            yield view(key)
            return
        yield view(key, "Reading your sample and its structure…", busy=True)
        try:
            sample = service.upload_sample(key, path)
            session = service.get_session(key)
            session.pending = None
            session.input_form = InputForm(
                title="Use your reference document",
                description="Choose the output and tell us what to change. "
                "Standard introductory text will be used unless you request "
                "custom wording.",
                fields=[
                    {
                        "id": "output_format",
                        "label": "Output format",
                        "type": "select",
                        "choices": ["DOCX", "PDF", "PPTX", "XLSX"],
                        "default": sample["format"].upper()
                        if sample["format"] in {"docx", "pdf", "pptx", "xlsx"}
                        else None,
                    },
                    {
                        "id": "sample_changes",
                        "label": "What should change?",
                        "type": "multiline",
                        "default": "Keep the current structure.",
                        "placeholder": "Sections to keep, remove, or add…",
                    },
                ],
            ).model_dump(mode="json")
            session.history.extend(
                [
                    {"role": "user", "content": f"Added sample: {Path(path).name}"},
                    {
                        "role": "assistant",
                        "content": (
                            f"Your {sample['format'].upper()} sample is ready. "
                            "Use the form below to choose the output and "
                            "describe any changes."
                        ),
                    },
                ]
            )
            yield view(key, "Sample added. Continue in the conversation.")
        except Exception as exc:
            logger.exception("Sample upload failed")
            yield view(key, request_error(exc))

    def data_upload(path, key):
        key, _ = get_session(key)
        if not path:
            yield view(key)
            return
        yield view(key, "Adding your data source…", busy=True)
        try:
            connection = service.upload_data(key, path)
            from report_agent.connectors.registry import describe_source

            details = describe_source(service.sources[connection])
            session = service.get_session(key)
            session.pending = None
            columns = ", ".join(details.get("columns", {}))
            session.history.extend(
                [
                    {"role": "user", "content": f"Added data: {Path(path).name}"},
                    {
                        "role": "assistant",
                        "content": (
                            f"Data is ready. Columns: {columns}. "
                            "Continue with the current form, or ask me to "
                            "build the draft when the content choices are agreed."
                        ),
                    },
                ]
            )
            yield view(key, "Data added. Confirm its selection rules in chat.")
        except Exception as exc:
            logger.exception("Data upload failed")
            yield view(key, request_error(exc))

    def accept(key, expected=None, queries_reviewed=False):
        key, session = get_session(key)
        try:
            with session.lock:
                if expected and expected != (session.draft, str(session.preview_path)):
                    raise ReportError(
                        "This preview has changed. Review the latest draft."
                    )
                service.onboarding.accept(session, queries_reviewed=queries_reviewed)
                session.history.append(
                    {
                        "role": "assistant",
                        "content": (
                            "Template saved. Tell me the dates or "
                            "filters for your next "
                            "report; the design and data bindings are ready to reuse."
                        ),
                    }
                )
            return view(key, "Template saved for future runs.")
        except ReportError as exc:
            return view(key, str(exc))
        except Exception as exc:
            logger.exception("Template acceptance failed")
            return view(key, request_error(exc))

    def confirm(key, expected=None):
        key, session = get_session(key)
        yield view(key, "Fetching data and rendering your report…", busy=True)
        try:
            with session.lock:
                if expected and session.pending != expected:
                    raise ValueError(
                        "These inputs changed. Review the latest proposal."
                    )
                result = service.onboarding.confirm(session)
                status = (
                    "Report ready to download."
                    if result.output_path
                    else "Render failed: "
                    + "; ".join(d.message for d in result.diagnostics)
                )
                session.history.append({"role": "assistant", "content": status})
            yield view(key, status)
        except Exception as exc:
            logger.exception("Report render failed")
            yield view(key, request_error(exc))

    def edit_parameters(key, expected):
        key, session = get_session(key)
        try:
            with session.lock:
                if session.pending != expected:
                    raise ReportError("These inputs changed. Use the latest proposal.")
                reference = expected["reference"]
                session.input_form = parameter_form(
                    service.onboarding.store.load(reference),
                    reference,
                    expected["parameters"],
                    title="Update report inputs",
                    description="Edit the values, then review them before rendering.",
                ).model_dump(mode="json")
                session.pending = None
            return view(key)
        except ReportError as exc:
            return view(key, str(exc))

    def reset(key):
        if key:
            service.remove_session(key)
        return (
            *view(None, "New conversation. Saved templates remain available."),
            "",
            None,
            None,
        )

    def use_saved(reference):
        if not reference:
            return ""
        definition = service.onboarding.store.load(reference)
        version = reference.rsplit("/", 1)[-1]
        if reference.startswith("drafts/"):
            return (
                f"Resume my draft '{definition.name}'. "
                "Help me preview it and finish onboarding."
            )
        return (
            f"Use my saved report '{definition.name}' ({version}). "
            "Help me confirm the parameters for a new run."
        )

    def saved_choices():
        return [
            (
                f"{item['name']} · {item['format'].upper()} · "
                + (
                    "Draft"
                    if item["reference"].startswith("drafts/")
                    else item["reference"].rsplit("/", 1)[-1]
                ),
                item["reference"],
            )
            for item in (
                service.onboarding.store.list() + service.onboarding.store.list_drafts()
            )
        ]

    with gr.Blocks(
        title="Report Studio", analytics_enabled=False, delete_cache=(3600, 86400)
    ) as app:
        with gr.Row(elem_id="topbar"):
            gr.HTML(
                '<div class="wordmark">◈ <strong>Report Studio</strong>'
                "<span> / conversation</span></div>"
            )
            new_button = gr.Button("New chat", size="sm", scale=0)
        state = gr.State(
            value=None, time_to_live=3600, delete_callback=service.remove_session
        )
        transcript = gr.State([])
        with gr.Column(elem_id="chat-thread"):

            @gr.render(inputs=transcript, queue=False, show_progress="hidden")
            def render_thread(events):
                if not any(event["kind"] != "activity" for event in events):
                    gr.HTML(
                        '<div id="welcome"><div class="agent-mark">◈</div>'
                        "<h1>What are we reporting on?</h1>"
                        "<p>Start with an idea, a sample, or a saved report.<br>"
                        "We’ll build it together, right here.</p></div>"
                    )
                for event in events:
                    event_id = event["id"]
                    kind = event["kind"]
                    classes = ["chat-event", "event-" + kind]
                    if kind == "message":
                        classes.append("from-" + event["role"])
                    with gr.Column(key=event_id, elem_classes=classes, scale=0):
                        if kind == "message":
                            gr.Markdown(
                                "You" if event["role"] == "user" else "◈ Report Studio",
                                elem_classes="speaker",
                            )
                            gr.HTML(chat_html(event["content"]), key=event_id + "-text")
                        elif kind == "report":
                            gr.Markdown("**Report preview**", elem_classes="card-title")
                            if event["gallery"]:
                                gr.Gallery(
                                    event["gallery"],
                                    columns=2,
                                    height=360,
                                    object_fit="contain",
                                    interactive=False,
                                    show_label=False,
                                    key=event_id + "-gallery",
                                )
                            for index, path in enumerate(event["files"]):
                                gr.DownloadButton(
                                    "↓ " + Path(path).name,
                                    value=path,
                                    key=f"{event_id}-file-{index}",
                                )
                            if event.get("reference"):
                                review = event.get("query_review", {})
                                queries = review.get("queries", {})
                                accepted = event.get("accepted")
                                if queries:
                                    gr.HTML(
                                        data_review_html(review),
                                        key=event_id + "-data-review",
                                    )
                                if accepted:
                                    version = accepted["reference"].rsplit("/", 1)[-1]
                                    gr.Markdown(
                                        f"✓ Template saved · {version}",
                                        elem_classes="report-saved",
                                        key=event_id + "-saved",
                                    )
                                with gr.Row(elem_classes="report-approval"):
                                    reviewed = gr.Checkbox(
                                        label="Queries and bindings reviewed"
                                        if accepted
                                        else "I reviewed the data and queries",
                                        value=bool(
                                            accepted and accepted["queries_reviewed"]
                                        ),
                                        visible=bool(queries),
                                        interactive=event["active"],
                                        key=event_id + "-reviewed",
                                        preserved_by_key=[],
                                        scale=1,
                                    )
                                    button = gr.Button(
                                        "Template saved"
                                        if accepted
                                        else "Accept template"
                                        if event["active"]
                                        else "Previous draft preview",
                                        visible=not bool(accepted),
                                        interactive=event["active"] and not queries,
                                        variant="primary",
                                        size="sm",
                                        scale=0,
                                        min_width=132,
                                        key=event_id + "-accept",
                                        preserved_by_key=[],
                                    )
                                expected = (event["reference"], event["preview"])

                                def bind_accept(expected):
                                    return lambda key, checked: accept(
                                        key, expected, checked
                                    )

                                reviewed.change(
                                    lambda checked, active=event["active"]: gr.update(
                                        interactive=bool(checked) and active
                                    ),
                                    [reviewed],
                                    button,
                                    queue=False,
                                )

                                button.click(
                                    bind_accept(expected),
                                    [state, reviewed],
                                    outputs,
                                    key=event_id + "-accept-click",
                                    **options,
                                )
                        elif kind == "parameters":
                            gr.Markdown("**Confirm report inputs**")
                            gr.Dataframe(
                                [
                                    [name.replace("_", " ").title(), str(value)]
                                    for name, value in event["proposal"][
                                        "parameters"
                                    ].items()
                                ],
                                headers=["Parameter", "Value"],
                                interactive=False,
                                show_label=False,
                                key=event_id + "-table",
                            )
                            button = gr.Button(
                                "Confirm parameters and render"
                                if event["active"]
                                else "Previous report inputs",
                                interactive=event["active"],
                                variant="primary",
                                key=event_id + "-confirm",
                                preserved_by_key=[],
                            )

                            def bind_confirm(expected):
                                def run(key):
                                    yield from confirm(key, expected)

                                return run

                            button.click(
                                bind_confirm(event["proposal"]),
                                [state],
                                outputs,
                                key=event_id + "-confirm-click",
                                **options,
                            )
                            edit = gr.Button(
                                "Edit inputs",
                                size="sm",
                                interactive=event["active"],
                                key=event_id + "-edit",
                                preserved_by_key=[],
                            )

                            def bind_edit(expected):
                                return lambda key: edit_parameters(key, expected)

                            edit.click(
                                bind_edit(event["proposal"]),
                                [state],
                                outputs,
                                key=event_id + "-edit-click",
                                **options,
                            )
                        elif kind == "input_form":
                            render_input_form(
                                event, state, outputs, options, submit_inputs
                            )
                        elif kind == "activity":
                            prefix = "◌ " if event.get("busy") else ""
                            gr.HTML(
                                plain_text_html(prefix + event["content"]),
                                elem_classes="activity-line",
                            )

        with gr.Column(elem_id="composer-shell"):
            with gr.Row(elem_id="starter-buttons"):
                known = gr.Button("Choose a report", size="sm", scale=0, min_width=0)
                uncertain = gr.Button(
                    "Help me get started", size="sm", scale=0, min_width=0
                )
            message = gr.Textbox(
                label="Message",
                show_label=False,
                lines=1,
                max_lines=6,
                placeholder="Describe a report or ask for a change…",
                elem_id="composer",
            )
            menu_state = gr.State(None)
            with gr.Column(visible=False, elem_id="attach-popover") as attach_panel:
                gr.Markdown("**Add to this conversation**")
                sample = gr.UploadButton(
                    "Reference document",
                    type="filepath",
                    size="sm",
                    file_types=[".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md"],
                )
                data = gr.UploadButton(
                    "Report data · CSV or Excel",
                    type="filepath",
                    size="sm",
                    file_types=[".csv", ".xlsx"],
                )
                gr.Markdown("**Try fictional example data**")
                with gr.Row():
                    demo_sample = gr.Button(
                        "Use sales sample",
                        size="sm",
                        interactive=(kit / "sales-example.docx").exists(),
                    )
                    demo_data = gr.Button(
                        "Use milestone data",
                        size="sm",
                        interactive=(kit / "milestones.xlsx").exists(),
                    )
            with gr.Column(visible=False, elem_id="saved-popover") as saved_panel:
                gr.Markdown("**Continue a report**")
                saved = gr.Dropdown(
                    label="Template or draft", choices=saved_choices(), value=None
                )
                refresh = gr.Button("Refresh library", size="sm")
            with gr.Row(elem_id="composer-toolbar"):
                attach_toggle = gr.Button(
                    "＋ Attach",
                    size="sm",
                    scale=0,
                    min_width=0,
                    elem_id="attach-toggle",
                )
                saved_toggle = gr.Button(
                    "Saved reports",
                    size="sm",
                    scale=0,
                    min_width=0,
                    elem_id="saved-toggle",
                )
                gr.HTML("<span></span>", elem_id="toolbar-spacer")
                send = gr.Button(
                    "Send",
                    variant="primary",
                    size="sm",
                    scale=0,
                    min_width=76,
                    elem_id="send",
                )
            status = gr.HTML("", visible=False)
            dismiss_menu = gr.Button("Close menus", elem_id="dismiss-menus")
            gr.Markdown(
                "Files and messages use your configured model endpoint.",
                elem_id="privacy",
            )
        outputs = [state, transcript, status, send]
        options = {
            "concurrency_id": "report-interactions",
            "concurrency_limit": 1,
            "show_progress": "hidden",
        }

        def toggle_menu(name, current):
            selected = name if current != name else None
            return (
                selected,
                gr.update(visible=selected == "attach"),
                gr.update(visible=selected == "saved"),
            )

        menu_outputs = [menu_state, attach_panel, saved_panel]
        attach_toggle.click(
            lambda current: toggle_menu("attach", current),
            [menu_state],
            menu_outputs,
            queue=False,
        )
        saved_toggle.click(
            lambda current: toggle_menu("saved", current),
            [menu_state],
            menu_outputs,
            queue=False,
        )

        def close_menu():
            return None, gr.update(visible=False), gr.update(visible=False)

        dismiss_menu.click(close_menu, outputs=menu_outputs, queue=False)

        send.click(
            chat, [message, state], [*outputs, message], api_name="chat", **options
        )
        message.submit(chat, [message, state], [*outputs, message], **options)
        sample.upload(
            sample_upload, [sample, state], outputs, api_name="upload_sample", **options
        ).then(close_menu, outputs=menu_outputs, queue=False)
        data.upload(
            data_upload, [data, state], outputs, api_name="upload_data", **options
        ).then(close_menu, outputs=menu_outputs, queue=False)
        new_button.click(
            reset,
            [state],
            [*outputs, message, sample, data],
            api_name="new_conversation",
            **options,
        )

        def use_demo_sample(key):
            yield from sample_upload(str(kit / "sales-example.docx"), key)

        def use_demo_data(key):
            yield from data_upload(str(kit / "milestones.xlsx"), key)

        demo_sample.click(use_demo_sample, [state], outputs, **options).then(
            close_menu, outputs=menu_outputs, queue=False
        )
        demo_data.click(use_demo_data, [state], outputs, **options).then(
            close_menu, outputs=menu_outputs, queue=False
        )
        known.click(
            lambda: "I need a monthly project status report. Help me choose a design.",
            outputs=message,
            queue=False,
        )
        uncertain.click(
            start_discovery,
            [state],
            outputs,
            api_name="start_discovery",
            **options,
        )
        saved.input(use_saved, [saved], message, queue=False).then(
            close_menu, outputs=menu_outputs, queue=False
        )
        refresh.click(
            lambda: gr.update(choices=saved_choices()), outputs=saved, queue=False
        )
    return app.queue()
