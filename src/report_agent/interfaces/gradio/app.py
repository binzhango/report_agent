"""Conversation and review workspace with state-aware acceptance controls."""

import logging
from pathlib import Path
from queue import Queue
from threading import Thread

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
        if key is None or key not in service.sessions:
            key = service.new_session()
        return key, service.sessions[key]

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
        return key, events, status, gr.update(interactive=not busy)

    def chat(message, key):
        key, _ = get_session(key)
        if not message.strip():
            yield (*view(key, "Write a message to get started."), message)
            return
        yield (
            *view(key, "Working on your report…", busy=True, user_message=message),
            "",
        )
        updates = Queue()

        def work():
            try:
                service.send(
                    key,
                    message,
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

    def sample_upload(path, key):
        key, _ = get_session(key)
        if not path:
            yield view(key)
            return
        yield view(key, "Reading your sample and its structure…", busy=True)
        try:
            sample = service.upload_sample(key, path)
            session = service.sessions[key]
            session.pending = None
            session.history.extend(
                [
                    {"role": "user", "content": f"Added sample: {Path(path).name}"},
                    {
                        "role": "assistant",
                        "content": (
                            f"Your {sample['format'].upper()} sample is ready. "
                            "What should change in the new report? Tell me "
                            "which sections to keep, the output format, and "
                            "where its tables or charts should get their data."
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
            session = service.sessions[key]
            session.pending = None
            columns = ", ".join(details.get("columns", {}))
            session.history.extend(
                [
                    {"role": "user", "content": f"Added data: {Path(path).name}"},
                    {
                        "role": "assistant",
                        "content": (
                            f"Data is ready. Columns: {columns}. "
                            "Tell me the selection rules or preview inputs, "
                            "or ask me to build the draft if those are already agreed."
                        ),
                    },
                ]
            )
            yield view(key, "Data added. Confirm its selection rules in chat.")
        except Exception as exc:
            logger.exception("Data upload failed")
            yield view(key, request_error(exc))

    def accept(key, expected=None):
        key, session = get_session(key)
        try:
            with session.lock:
                if expected and expected != (session.draft, str(session.preview_path)):
                    raise ValueError(
                        "This preview has changed. Review the latest draft."
                    )
                service.onboarding.accept(session)
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
        except ValueError as exc:
            return view(key, str(exc))

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
                    with gr.Column(key=event_id, elem_classes=classes):
                        if kind == "message":
                            gr.Markdown(
                                "You" if event["role"] == "user" else "◈ Report Studio",
                                elem_classes="speaker",
                            )
                            gr.Markdown(event["content"], key=event_id + "-text")
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
                                button = gr.Button(
                                    "Accept template"
                                    if event["active"]
                                    else "Previous draft preview",
                                    interactive=event["active"],
                                    variant="primary",
                                    key=event_id + "-accept",
                                    preserved_by_key=[],
                                )
                                expected = (event["reference"], event["preview"])

                                def bind_accept(expected):
                                    return lambda key: accept(key, expected)

                                button.click(
                                    bind_accept(expected),
                                    [state],
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
                        elif kind == "activity":
                            prefix = "◌ " if event.get("busy") else ""
                            gr.Markdown(
                                prefix + event["content"], elem_classes="activity-line"
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
                lines=2,
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
            status = gr.Markdown("", visible=False)
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
            lambda: (
                "I need a report, but don't know what it should include. "
                "Help me step by step."
            ),
            outputs=message,
            queue=False,
        )
        saved.input(use_saved, [saved], message, queue=False).then(
            close_menu, outputs=menu_outputs, queue=False
        )
        refresh.click(
            lambda: gr.update(choices=saved_choices()), outputs=saved, queue=False
        )
    return app.queue()
