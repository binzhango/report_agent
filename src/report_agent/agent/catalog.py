"""Application-owned report designs exposed to the agent and the user."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ReportTemplate:
    id: str
    name: str
    description: str
    outline: tuple[str, ...]
    color: str


TEMPLATES = (
    ReportTemplate(
        "executive",
        "Executive brief",
        "A concise report for decision makers, business reviews and proposals.",
        ("Executive summary", "Key findings", "Recommendations"),
        "#16324F",
    ),
    ReportTemplate(
        "project",
        "Project update",
        "Progress, milestones, risks and next steps for a team or stakeholder.",
        ("Status", "Progress and milestones", "Risks", "Next steps"),
        "#17665B",
    ),
    ReportTemplate(
        "research",
        "Research report",
        "A structured exploration of a topic, with evidence and limitations.",
        ("Overview", "Analysis", "Limitations", "Conclusions"),
        "#673C64",
    ),
)


def get_template(template_id: str) -> ReportTemplate:
    for template in TEMPLATES:
        if template.id == template_id:
            return template
    raise ValueError(f"Unknown report template: {template_id}")


def catalog_context() -> list[dict]:
    return [asdict(template) for template in TEMPLATES]
