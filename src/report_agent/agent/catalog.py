"""Application-owned report designs exposed to the agent and the user."""

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ReportTemplate:
    id: str
    name: str
    description: str
    outline: tuple[str, ...]
    color: str
    demo_rows: tuple[dict[str, str], ...] = field(
        default_factory=lambda: ({"Item": "Example record", "Status": "Illustrative"},)
    )


TEMPLATES = (
    ReportTemplate(
        "executive",
        "Executive brief",
        "A concise report for decision makers, business reviews and proposals.",
        ("Executive summary", "Key findings", "Recommendations"),
        "#16324F",
        (
            {"Measure": "Delivery", "Example result": "On schedule"},
            {"Measure": "Budget", "Example result": "Within plan"},
        ),
    ),
    ReportTemplate(
        "project",
        "Project update",
        "Progress, milestones, risks and next steps for a team or stakeholder.",
        ("Status", "Progress and milestones", "Risks", "Next steps"),
        "#17665B",
        (
            {"Milestone": "Design review", "Owner": "Maya", "Status": "Complete"},
            {"Milestone": "Pilot launch", "Owner": "Omar", "Status": "In progress"},
            {"Milestone": "Team handover", "Owner": "Elena", "Status": "Planned"},
        ),
    ),
    ReportTemplate(
        "research",
        "Research report",
        "A structured exploration of a topic, with evidence and limitations.",
        ("Overview", "Analysis", "Limitations", "Conclusions"),
        "#673C64",
        (
            {
                "Observation": "Response time",
                "Evidence": "Example survey",
                "Next step": "Validate findings",
            },
            {
                "Observation": "Coverage",
                "Evidence": "Example review",
                "Next step": "Expand sample",
            },
        ),
    ),
)


def get_template(template_id: str) -> ReportTemplate:
    for template in TEMPLATES:
        if template.id == template_id:
            return template
    raise ValueError(f"Unknown report template: {template_id}")


def catalog_context() -> list[dict]:
    return [asdict(template) for template in TEMPLATES]
