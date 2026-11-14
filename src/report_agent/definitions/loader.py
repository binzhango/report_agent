"""Human-readable definitions; runtime parameter values live in run records."""

from pathlib import Path

import yaml

from report_agent.definitions.models import ReportDefinition


def load_definition(path: Path) -> ReportDefinition:
    return ReportDefinition.model_validate(yaml.safe_load(path.read_text()))


def save_definition(definition: ReportDefinition, path: Path) -> None:
    path.write_text(yaml.safe_dump(definition.model_dump(mode="json"), sort_keys=False))
