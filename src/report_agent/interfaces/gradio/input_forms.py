"""Native controls for structured agent questions inside the transcript."""


def unpack_answers(fields, values):
    answers, index = {}, 0
    for field in fields:
        value = values[index]
        index += 1
        if field.get("allow_other"):
            other = values[index]
            index += 1
            if value == "Other…":
                value = other
        answers[field["id"]] = value
    return answers


def render_input_form(event, state, outputs, options, submit):
    import gradio as gr

    form, active = event["form"], event["active"]
    answered = event.get("answers")
    prefix = event["id"]
    gr.Markdown(form["title"], elem_classes="input-form-title")
    if form.get("description"):
        gr.Markdown(form["description"], elem_classes="input-form-description")
    gr.Markdown("Required fields are marked *.", elem_classes="input-form-hint")
    controls = []
    for field in form["fields"]:
        value = (answered or {}).get(field["id"], field.get("default"))
        args = {
            "label": field["label"]
            + (" *" if field.get("required", True) else " (optional)"),
            "info": field.get("help") or None,
            "interactive": active,
            "key": prefix + "-" + field["id"],
        }
        # Preserve partially filled values across progress/status renders. Once
        # answered, the submitted snapshot supplies the immutable display values.
        if answered is not None:
            args["preserved_by_key"] = []
        kind = field.get("type", "text")
        if kind == "date":
            widget = gr.DateTime(value=value, type="string", include_time=False, **args)
        elif kind in {"number", "integer"}:
            widget = gr.Number(
                value=value, precision=0 if kind == "integer" else None, **args
            )
        elif kind == "boolean":
            widget = gr.Radio(
                [("Yes", "yes"), ("No", "no")],
                value=None if value is None else "yes" if value else "no",
                **args,
            )
        elif kind == "select":
            choices = field["choices"]
            custom = value is not None and str(value) not in choices
            widget = gr.Dropdown(
                choices=choices + (["Other…"] if field.get("allow_other") else []),
                value="Other…" if custom else str(value) if value is not None else None,
                **args,
            )
        else:
            widget = gr.Textbox(
                value=value,
                lines=3 if kind == "multiline" else 1,
                max_lines=8 if kind == "multiline" else 1,
                placeholder=field.get("placeholder")
                or (
                    "YYYY-MM or November 2026"
                    if kind == "month"
                    else "Type your answer…"
                ),
                **args,
            )
        controls.append(widget)
        if field.get("allow_other"):
            other = gr.Textbox(
                label="Other — " + field["label"],
                value=value if custom else "",
                visible=custom,
                interactive=active,
                key=prefix + "-other-" + field["id"],
                placeholder="Type your answer…",
            )
            widget.change(
                lambda value: gr.update(visible=value == "Other…"),
                [widget],
                other,
                queue=False,
            )
            controls.append(other)
    error = gr.Markdown("", elem_classes="input-form-error", key=prefix + "-error")
    button = gr.Button(
        ("Review parameters" if form.get("report_reference") else "Continue")
        if active
        else "Answers submitted"
        if answered is not None
        else "Previous questions",
        variant="primary",
        interactive=active,
        key=prefix + "-submit",
        preserved_by_key=[],
    )

    def answer(key, *values):
        yield from submit(key, form["id"], unpack_answers(form["fields"], values))

    button.click(
        answer,
        [state, *controls],
        [*outputs, error],
        key=prefix + "-submit-click",
        **options,
    )
