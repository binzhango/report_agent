"""Calendar-month shortcuts; boundary arithmetic never depends on a model."""

import re
from datetime import date, datetime, timedelta

from report_agent.definitions.parameters import DateRange
from report_agent.errors import ReportError


def normalize_month(value):
    if isinstance(value, str):
        for pattern in ("%Y-%m", "%B %Y", "%b %Y"):
            try:
                parsed = datetime.strptime(value.strip(), pattern)
                return f"{parsed.year:04d}-{parsed.month:02d}"
            except ValueError:
                pass
    raise ReportError(
        "Use YYYY-MM or a month and year, such as November 2026.", code="invalid_month"
    )


def month_dates(span, month):
    year, number = map(int, normalize_month(month).split("-"))
    start = date(year, number, 1)
    try:
        following = date(year + (number == 12), number % 12 + 1, 1)
    except ValueError as exc:
        raise ReportError(
            "This month is outside the supported date range.", code="invalid_month"
        ) from exc
    end = following - timedelta(days=1) if span.end_inclusive else following
    return {span.start: start.isoformat(), span.end: end.isoformat()}


def _legacy_semantics(definition, rule):
    """Recognize simple saved bounds; ambiguous data queries get no shortcut."""
    bounds, unknown = set(), False
    for query in definition.queries.values():
        for key, parameter in query.parameter_bindings.items():
            if parameter != rule.after:
                continue
            if key in query.filters:
                operator = query.filters[key].op
                if operator in {"lt", "le"}:
                    bounds.add(operator == "le")
                else:
                    unknown = True
                continue
            sql = re.sub(
                r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|--[^\n]*|/\*.*?\*/",
                " ",
                query.query,
                flags=re.S,
            )
            # Dollar-quoted PostgreSQL bodies are outside this small recognizer.
            if re.search(r"\$[A-Za-z_0-9]*\$", sql):
                unknown = True
                continue
            matches = re.findall(r"(<=|<)\s*:" + re.escape(key) + r"\b", sql)
            starts = [
                name
                for name, target in query.parameter_bindings.items()
                if target == rule.before
            ]
            between = any(
                re.search(
                    r"\bBETWEEN\s*:"
                    + re.escape(start)
                    + r"\s+AND\s*:"
                    + re.escape(key)
                    + r"\b",
                    sql,
                    re.I,
                )
                for start in starts
            )
            if matches or between:
                bounds.update(match == "<=" for match in matches)
                if between:
                    bounds.add(True)
            else:
                unknown = True
    if unknown or len(bounds) > 1:
        return None
    if bounds:
        return bounds.pop()
    # Text-only legacy reports have no data-query boundary to contradict. Their
    # standard monthly shortcut uses an explicitly labeled exclusive end date.
    description = definition.parameters[rule.after].description
    if re.search(r"\bexclusive\b|\bnot\s+inclusive\b", description, re.I):
        return False
    return bool(re.search(r"\binclusive\b", description, re.I))


def calendar_ranges(definition):
    if definition.date_ranges:
        return list(definition.date_ranges)
    spans, used = [], set()
    for rule in definition.parameter_order:
        if {rule.before, rule.after} & used:
            continue
        if any(
            definition.parameters[name].type != "date"
            for name in (rule.before, rule.after)
        ):
            continue
        inclusive = _legacy_semantics(definition, rule)
        if inclusive is None:
            continue
        spans.append(
            DateRange(start=rule.before, end=rule.after, end_inclusive=inclusive)
        )
        used.update((rule.before, rule.after))
    return spans


def expand_report_month(definition, supplied, month):
    spans = calendar_ranges(definition)
    if len(spans) != 1:
        raise ReportError(
            "Use the parameter form to choose dates for this report; "
            "a single calendar range is not defined.",
            code="ambiguous_month_range",
        )
    dates = month_dates(spans[0], month)
    if any(
        name in supplied and supplied[name] != value for name, value in dates.items()
    ):
        raise ReportError(
            "The reporting month conflicts with supplied dates. "
            "Supply a month or custom dates, not both.",
            code="month_date_conflict",
        )
    for name, value in dates.items():
        definition.parameters[name].validate_value(value)
    return {**supplied, **dates}
