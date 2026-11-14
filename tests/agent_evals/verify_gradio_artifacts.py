"""Check actual downloads from the documented browser-driven demo journeys."""

import argparse
import json
from pathlib import Path

from report_agent.ingestion.samples import extract_sample


def verify(root, journey="all"):
    records = []
    for path in (root / "runs").glob("*/run.json"):
        record = json.loads(path.read_text())
        if record.get("status") == "succeeded" and record["reference"].startswith(
            "accepted/"
        ):
            records.append(record)
    checks = []
    for record in records:
        output = Path(record["output"])
        text = extract_sample(output)["text"]
        if output.suffix == ".docx" and "Pilot launch" in text:
            assert "Training complete" in text and "Release sign-off" in text
            assert "Design approval" not in text and "Data migration" not in text
            checks.append(
                {
                    "journey": "known_report",
                    "output": str(output),
                    "parameters": record["parameters"],
                }
            )
        elif output.suffix == ".pdf" and "14890" in text.replace(",", ""):
            assert "9730" in text.replace(",", "")
            assert "12450" not in text.replace(",", "")
            checks.append(
                {
                    "journey": "uploaded_sample",
                    "output": str(output),
                    "parameters": record["parameters"],
                }
            )
        elif output.suffix == ".pptx" and "Tax correction" in text:
            assert "Card declined" in text and "Export receipt" in text
            assert "Duplicate invoice" not in text and "Closed dispute" not in text
            assert "Login issue" not in text
            checks.append(
                {
                    "journey": "guided_discovery",
                    "output": str(output),
                    "parameters": record["parameters"],
                }
            )
    (root / "verification.json").write_text(json.dumps(checks, indent=2))
    for check in checks:
        print(check["journey"], check["output"])
    required = (
        {"known_report", "uploaded_sample", "guided_discovery"}
        if journey == "all"
        else {journey}
    )
    missing = required - {c["journey"] for c in checks}
    if missing:
        raise AssertionError(
            f"Missing successful repeat-run artifacts: {sorted(missing)}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root", type=Path, nargs="?", default=Path("output/gradio_verification")
    )
    parser.add_argument(
        "--journey",
        default="all",
        choices=["all", "known_report", "uploaded_sample", "guided_discovery"],
    )
    args = parser.parse_args()
    verify(args.root, args.journey)
