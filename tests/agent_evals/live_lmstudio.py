"""Opt-in live evaluation against an OpenAI-compatible local model server."""

import argparse
import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from langchain_openai import ChatOpenAI

from report_agent.agent.config import AgentConfig
from report_agent.agent.factory import create_report_agent
from report_agent.application.onboarding import Onboarding, OnboardingService
from report_agent.application.report_runs import ReportRuns
from report_agent.connectors.sql import SqlSource
from report_agent.definitions.models import ReportDefinition
from report_agent.ingestion.samples import extract_sample
from report_agent.storage.report_definitions import ReportStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    parser.add_argument("--authoring", action="store_true")
    parser.add_argument("--authoring-only", action="store_true")
    args = parser.parse_args()
    root = Path("output/agent_evals") / uuid4().hex
    root.mkdir(parents=True)
    store = ReportStore(root / "library")
    sources = {}
    runs = ReportRuns(store, sources, root / "runs")
    onboarding = OnboardingService(store, runs)
    config = AgentConfig(args.model, Path(".agents/skills").resolve(), args.base_url)
    model = ChatOpenAI(
        model=args.model,
        base_url=args.base_url,
        api_key="lm-studio",
        temperature=0,
        max_tokens=4096,
        timeout=120,
        max_retries=0,
        use_responses_api=False,
    )
    records = []

    def turn(session, prompt):
        graph = create_report_agent(config, session, onboarding, sources, model=model)
        seen = 0
        messages = []
        for state in graph.stream(
            {"messages": [{"role": "user", "content": prompt}]},
            config={"configurable": {"thread_id": session.id}, "recursion_limit": 30},
            stream_mode="values",
        ):
            messages = state["messages"]
            for message in messages[seen:]:
                if getattr(message, "tool_calls", None):
                    print(
                        "tools:",
                        [call["name"] for call in message.tool_calls],
                        flush=True,
                    )
                elif message.type == "tool":
                    print(
                        "tool result:",
                        message.name,
                        str(message.content)[:160],
                        flush=True,
                    )
            seen = len(messages)
        final = str(messages[-1].content)
        print("assistant:", final, flush=True)
        record = {
            "prompt": prompt,
            "response": final,
            "tools": [
                call["name"]
                for message in messages
                for call in getattr(message, "tool_calls", [])
            ],
            "pending": session.pending,
            "draft": session.draft,
        }
        records.append(record)
        (root / "results.json").write_text(json.dumps(records, indent=2))
        return record

    if not args.authoring_only:
        discovery = turn(
            Onboarding(),
            (
                "I manage a small shop and don't know what report I need. "
                "Help me work it out step by step. Ask me about the purpose first."
            ),
        )
        assert "read_file" in discovery["tools"], "Agent skipped discovery instructions"
        assert "?" in discovery["response"], "Agent did not ask a discovery question"
        assert not discovery["draft"], (
            "Agent created a template before gathering intent"
        )

    definition = ReportDefinition.model_validate(
        {
            "id": "monthly_update",
            "name": "Monthly update",
            "layout": {
                "title": "Monthly update",
                "format": "docx",
                "blocks": [
                    {
                        "name": "intro",
                        "heading": "Overview",
                        "text": "Fixed agreed introduction.",
                    },
                ],
            },
            "parameters": {
                "start_date": {"type": "date"},
                "end_date": {"type": "date"},
                "region": {"type": "string"},
            },
            "parameter_order": [{"before": "start_date", "after": "end_date"}],
            "text_bindings": {
                "title": "Update for {region}: {start_date} to {end_date}"
            },
        }
    )
    draft = store.draft(definition)
    preview = runs.run(
        draft,
        {"start_date": "2026-09-01", "end_date": "2026-10-01", "region": "Europe"},
    )
    if not preview.output_path:
        raise RuntimeError(preview.diagnostics)
    accepted = store.accept(draft, preview.output_path)
    session = Onboarding()
    if not args.authoring_only:
        repeated = turn(
            session,
            (
                f"Use my accepted monthly update {accepted} for Europe, October 2026. "
                "The end date is exclusive. Keep its fixed text and design. "
                "Prepare the parameters for confirmation."
            ),
        )
        expected = {
            "start_date": "2026-10-01",
            "end_date": "2026-11-01",
            "region": "Europe",
        }
        assert repeated["pending"] and repeated["pending"]["parameters"] == expected
        assert "create_draft" not in repeated["tools"]
        result = onboarding.confirm(session)
        assert result.output_path, result.diagnostics
        print("Live discovery and repeat-run checks passed:", root, flush=True)

    if args.authoring or args.authoring_only:
        database = root.resolve() / "sales.db"
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE sales (day TEXT, region TEXT, revenue INTEGER)"
            )
            connection.executemany(
                "INSERT INTO sales VALUES (?, ?, ?)",
                [
                    ("2026-10-15", "Europe", 120),
                    ("2026-10-15", "Asia", 90),
                    ("2026-11-15", "Europe", 150),
                    ("2026-11-15", "Asia", 110),
                ],
            )
        sources["sales_db"] = SqlSource(f"sqlite:///{database}")
        session = Onboarding(sample=extract_sample(preview.output_path))
        authored = turn(
            session,
            (
                "Create a new DOCX report named Sales summary with id sales_summary. "
                "Use my uploaded sample's simple narrative structure and its fixed "
                "introduction. Add a table headed Revenue by region. I confirm these "
                "content choices. The configured sales_db source is SQLite with table "
                "sales(day TEXT, region TEXT, revenue INTEGER). Sum revenue by region, "
                "ordered by region, for start_date inclusive to end_date exclusive. "
                "Save those two dates as required runtime parameters, with the "
                "start before the end. For the preview use 2026-10-01 to 2026-11-01. "
                "Use actual data from this source. Create and render the draft for "
                "my review; do not accept it on my behalf."
            ),
        )
        assert "create_draft" in authored["tools"]
        assert session.draft and session.preview_reference == session.draft
        assert session.preview_path and session.preview_path.is_file()
        saved = onboarding.accept(session)
        result = runs.run(saved, {"start_date": "2026-11-01", "end_date": "2026-12-01"})
        assert result.output_path, result.diagnostics
        content = extract_sample(result.output_path)["text"]
        assert "150" in content and "110" in content
        print(
            "Live authoring, acceptance, and refreshed query check passed:",
            root,
            flush=True,
        )


if __name__ == "__main__":
    main()
