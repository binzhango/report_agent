"""Native controls for structured agent questions inside the transcript."""

from report_agent.definitions.calendar_months import month_dates
from report_agent.definitions.parameters import DateRange
from report_agent.errors import ReportError
from report_agent.interfaces.gradio.safe_text import plain_text_html


def month_input_state(span, values):
    start, end = values.get(span.start), values.get(span.end)
    if start:
        candidate = str(start)[:7]
        try:
            expected = month_dates(span, candidate)
            if start == expected[span.start] and (
                end is None or end == expected[span.end]
            ):
                return "month", candidate
        except ReportError:
            pass
    return ("month", None) if start is None and end is None else ("dates", None)


def unpack_form_answers(form, values):
    count = sum(2 if f.get("allow_other") else 1 for f in form["fields"])
    answers = unpack_answers(form["fields"], values[:count])
    for index, data in enumerate(form.get("month_ranges", [])):
        mode, month = values[count + index * 2 : count + index * 2 + 2]
        if mode == "month":
            answers.update(month_dates(DateRange.model_validate(data), month))
    return answers


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
    gr.HTML(plain_text_html(form["title"]), elem_classes="input-form-title")
    if form.get("description"):
        gr.HTML(
            plain_text_html(form["description"]), elem_classes="input-form-description"
        )
    gr.Markdown("Required fields are marked *.", elem_classes="input-form-hint")
    shortcuts, visibility = [], {}
    displayed = {
        field["id"]: (answered or {}).get(field["id"], field.get("default"))
        for field in form["fields"]
    }
    for index, data in enumerate(form.get("month_ranges", [])):
        span = DateRange.model_validate(data)
        mode, month = month_input_state(span, displayed)
        choice = gr.Radio(
            [("Calendar month", "month"), ("Custom dates", "dates")],
            value=mode,
            label="Reporting period"
            if index == 0
            else "Reporting period " + str(index + 1),
            interactive=active,
            key=prefix + f"-month-mode-{index}",
        )
        month_control = gr.Textbox(
            value=month,
            label="Reporting month",
            placeholder="November 2026 or 2026-11",
            visible=mode == "month",
            interactive=active,
            key=prefix + f"-month-{index}",
        )
        gr.HTML(
            plain_text_html(
                "Calendar-month mode fills both dates automatically. "
                + (
                    "The end date is included."
                    if span.end_inclusive
                    else "The end date is excluded."
                )
            ),
            elem_classes="input-field-help",
        )
        shortcuts.append((span, choice, month_control))
        visibility[span.start] = visibility[span.end] = mode == "dates"
    controls = []
    widgets = {}
    for field in form["fields"]:
        value = (answered or {}).get(field["id"], field.get("default"))
        args = {
            "label": field["label"]
            + (" *" if field.get("required", True) else " (optional)"),
            "info": None,
            "interactive": active,
            "key": prefix + "-" + field["id"],
            "visible": visibility.get(field["id"], True),
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
        widgets[field["id"]] = widget
        if field.get("help"):
            gr.HTML(plain_text_html(field["help"]), elem_classes="input-field-help")
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
    for span, choice, month_control in shortcuts:
        choice.change(
            lambda mode: (
                gr.update(visible=mode == "month"),
                gr.update(visible=mode == "dates"),
                gr.update(visible=mode == "dates"),
            ),
            [choice],
            [month_control, widgets[span.start], widgets[span.end]],
            queue=False,
        )
        controls.extend([choice, month_control])
    error = gr.HTML("", elem_classes="input-form-error", key=prefix + "-error")
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
        try:
            answers = unpack_form_answers(form, values)
        except ReportError as exc:
            yield *[gr.skip() for _ in outputs], plain_text_html(str(exc))
            return
        yield from submit(key, form["id"], answers)

    button.click(
        answer,
        [state, *controls],
        [*outputs, error],
        key=prefix + "-submit-click",
        **options,
    )
