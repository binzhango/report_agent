"""Map table overflow line ranges back to generated input fragments."""

import re

from report_agent.models.results import Diagnostic


def compile_warnings(details: str, source: str) -> tuple[Diagnostic, ...]:
    spans = []
    opened = {}
    for number, line in enumerate(source.splitlines(), 1):
        marker = re.fullmatch(
            r"% REPORT_AGENT_TABLE_(BEGIN|END) ([A-Za-z][A-Za-z0-9_]*)", line
        )
        if marker:
            kind, name = marker.groups()
            if kind == "BEGIN":
                opened[name] = number
            elif name in opened:
                spans.append((opened.pop(name), number, name))
    diagnostics = []
    for line in dict.fromkeys(details.splitlines()):
        if "Warning:" not in line and "Overfull \\" not in line:
            continue
        overflow = re.search(r"Overfull \\hbox.*?at lines? (\d+)(?:--(\d+))?", line)
        names = set()
        if overflow:
            start, end = int(overflow[1]), int(overflow[2] or overflow[1])
            names = {
                name
                for begin, finish, name in spans
                if start <= finish and end >= begin
            }
        if names:
            diagnostics.extend(
                Diagnostic(
                    "compilation", "table_overflow", line.strip(), input_name=name
                )
                for name in sorted(names)
            )
        else:
            diagnostics.append(
                Diagnostic(
                    "compilation", "latex_warning", line.strip(), severity="warning"
                )
            )
    return tuple(diagnostics)
