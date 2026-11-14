"""Append report artifacts to the turn that produced them, preserving history."""

from copy import deepcopy


def snapshot(session, status="", *, busy=False):
    events = session.display_events
    seen_messages = sum(e["kind"] == "message" for e in events)
    for index, message in enumerate(session.history[seen_messages:], seen_messages):
        events.append(
            {"id": f"{session.id}-message-{index}", "kind": "message", **message}
        )
    seen_files = {p for e in events for p in e.get("files", [])}
    files = [p for p in session.files if p not in seen_files]
    seen_images = {p for e in events for p, _ in e.get("gallery", [])}
    images = [(p, title) for p, title in session.gallery if p not in seen_images]
    if files or images:
        events.append(
            {
                "id": f"{session.id}-report-{len(events)}",
                "kind": "report",
                "files": files,
                "gallery": images,
                "reference": (
                    session.preview_reference
                    if session.draft
                    and session.preview_reference == session.draft
                    and str(session.preview_path) in files
                    else None
                ),
                "preview": str(session.preview_path) if session.preview_path else None,
            }
        )
    if session.pending:
        previous = next(
            (e for e in reversed(events) if e["kind"] == "parameters"), None
        )
        if (
            not previous
            or previous["proposal"] != session.pending
            or previous.get("resolved")
        ):
            events.append(
                {
                    "id": f"{session.id}-parameters-{len(events)}",
                    "kind": "parameters",
                    "proposal": deepcopy(session.pending),
                }
            )
    else:
        for event in events:
            if event["kind"] == "parameters":
                event["resolved"] = True
    result = deepcopy(events)
    latest_parameters = next(
        (e["id"] for e in reversed(events) if e["kind"] == "parameters"), None
    )
    for event in result:
        event["active"] = not busy and (
            event["kind"] == "parameters"
            and not event.get("resolved", False)
            and event["proposal"] == session.pending
            and event["id"] == latest_parameters
            or event["kind"] == "report"
            and bool(session.draft)
            and event.get("reference") == session.draft
            and event.get("preview") == str(session.preview_path)
            and session.preview_reference == session.draft
        )
    if status and (
        busy or not session.history or status != session.history[-1]["content"]
    ):
        result.append(
            {"id": "activity", "kind": "activity", "content": status, "busy": busy}
        )
    return result
