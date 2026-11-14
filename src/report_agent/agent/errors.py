"""Public tool errors: never forward exception strings or external resources."""

from pydantic import ValidationError

from report_agent.errors import ReportError


def public_tool_error(exc):
    from httpx import HTTPError
    from sqlalchemy.exc import SQLAlchemyError

    if isinstance(exc, ReportError):
        return {"kind": "ReportError", "code": exc.code, "error": str(exc)}
    if isinstance(exc, ValidationError):
        from report_agent.application.input_forms import InputForm
        from report_agent.definitions.models import ReportDefinition

        fields = set()
        for model in (ReportDefinition, InputForm):
            schema = model.model_json_schema()
            fields.update(schema.get("properties", {}))
            for definition in schema.get("$defs", {}).values():
                fields.update(definition.get("properties", {}))
        issues = [
            {
                "field": ".".join(
                    str(part) if isinstance(part, int) or part in fields else "entry"
                    for part in issue["loc"]
                )
                or "definition",
                "type": issue["type"],
                **(
                    {
                        "error": str(issue["ctx"]["error"]),
                        "code": issue["ctx"]["error"].code,
                    }
                    if isinstance(issue.get("ctx", {}).get("error"), ReportError)
                    else {
                        "error": {
                            "missing": "This field is required.",
                            "literal_error": "Choose a value declared by the schema.",
                            "string_pattern_mismatch": "Use the format declared "
                            "by the schema.",
                        }.get(
                            issue["type"],
                            "Invalid value for this field; check report_contract.",
                        ),
                        "code": "schema_" + issue["type"],
                    }
                ),
            }
            for issue in exc.errors(
                include_input=False, include_context=True, include_url=False
            )
        ]
        return {
            "kind": "ValidationError",
            "issues": issues,
            "error": "Definition validation failed. Check report_contract, parameter "
            "types/order, declared bindings, and table/chart block requirements.",
        }
    if isinstance(exc, SQLAlchemyError):
        kind, message = (
            "DatabaseError",
            (
                "Database request failed. Check the configured source, query schema, "
                "permissions, and execution limits with the operator."
            ),
        )
    elif isinstance(exc, HTTPError):
        kind, message = (
            "HttpError",
            (
                "API request failed. Ask the operator to check endpoint availability, "
                "authentication, and response status."
            ),
        )
    elif isinstance(exc, OSError):
        kind, message = "FileError", "A required file is unavailable or unreadable."
    elif isinstance(exc, KeyError):
        kind, message = (
            "MissingResource",
            (
                "A source, sheet, field, or report was not found. "
                "Inspect the available report context and source schema."
            ),
        )
    elif isinstance(exc, ValueError):
        kind, message = (
            "InvalidRequest",
            (
                "Invalid report request. Check the report contract, required "
                "parameters, date order, source filters/columns, data bounds, "
                "and preview prerequisites."
            ),
        )
    else:
        kind, message = (
            "InternalError",
            "The report operation failed. Ask the operator to investigate.",
        )
    return {"kind": kind, "error": message}
