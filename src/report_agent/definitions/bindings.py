"""Bind validated values without interpolating query source."""

from report_agent.definitions.parameters import resolve_parameters
from report_agent.resolution.models import QuerySource


def bind_queries(definition, supplied):
    params = resolve_parameters(
        definition.parameters, supplied, definition.parameter_order
    )
    queries = {}
    for name, binding in definition.queries.items():
        missing = set(binding.parameter_bindings.values()) - params.keys()
        if missing:
            raise ValueError(f"Query {name} requires parameters: {sorted(missing)}")
        queries[name] = QuerySource(
            connection=binding.connection,
            query=binding.query,
            params={
                key: params[value] for key, value in binding.parameter_bindings.items()
            },
            row_limit=binding.row_limit,
        )
    return params, queries
