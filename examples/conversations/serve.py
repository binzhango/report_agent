"""Start Gradio with isolated demo storage and fictional sales/support sources."""

import argparse
import logging
from pathlib import Path

from prepare import database

from report_agent.agent.config import AgentConfig
from report_agent.application.conversation import ConversationService
from report_agent.application.onboarding import OnboardingService
from report_agent.application.report_runs import ReportRuns
from report_agent.connectors.sql import SqlSource
from report_agent.interfaces.gradio.app import create_app
from report_agent.interfaces.gradio.theme import launch_options
from report_agent.storage.report_definitions import ReportStore


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--root", type=Path, default=Path("output/conversation_demo"))
    args = parser.parse_args()
    path = database(args.root)
    sources = {
        name: SqlSource(f"sqlite:///{path}") for name in ("sales_db", "support_db")
    }
    store = ReportStore(args.root / "library")
    onboarding = OnboardingService(
        store, ReportRuns(store, sources, args.root / "runs")
    )
    service = ConversationService(AgentConfig.from_environment(), onboarding, sources)
    create_app(service).launch(
        server_name="127.0.0.1",
        server_port=args.port,
        share=False,
        max_file_size="20mb",
        **launch_options(),
    )


if __name__ == "__main__":
    main()
