"""Thin session adapter for Gradio; domain decisions belong to the agent."""

import json
import logging
import re
import shutil
from pathlib import Path
from threading import Lock
from uuid import uuid4

from report_agent.application.onboarding import Onboarding
from report_agent.connectors.files import FileSource
from report_agent.ingestion.samples import extract_sample

logger = logging.getLogger(__name__)


class EmptyModelResponse(ValueError):
    """The model finished without a usable assistant message."""


class ConversationService:
    """Single-user local service, not a tenant-isolated session store.

    Gradio serializes mutations with report-interactions/concurrency_limit=1.
    The registry lock protects session lookup/lifecycle; session.lock serializes
    each turn (including its model call). Progress snapshots run on that same
    worker. Shared source registries and UI snapshots rely on serialized UI
    mutations; callers must not treat this as a general concurrent web service.
    """

    def __init__(self, config, onboarding, sources, *, agent_factory=None):
        self.config, self.onboarding, self.sources = config, onboarding, sources
        self.sessions, self.agents = {}, {}
        self.source_labels = {}
        self.lock = Lock()
        self.agent_factory = agent_factory
        if agent_factory is None:
            from report_agent.agent.factory import initialize_harness

            initialize_harness(config.model)
        for path in (onboarding.store.root / "sources").glob("*/source.json"):
            data = json.loads(path.read_text())
            sources[data["name"]] = FileSource(
                path.parent / data["file"], filters=data.get("filters")
            )
            self.source_labels[data["name"]] = data.get(
                "original_name", "Uploaded workbook"
            )

    def new_session(self):
        session = Onboarding()
        with self.lock:
            session.source_labels.update(self.source_labels)
            self.sessions[session.id] = session
        return session.id

    def remove_session(self, session_id):
        with self.lock:
            self.agents.pop(session_id, None)
            self.sessions.pop(session_id, None)

    def get_session(self, session_id):
        with self.lock:
            return self.sessions[session_id]

    def send(self, session_id, message, *, display_message=None, progress=None):
        session = self.get_session(session_id)
        if not message.strip() or len(message) > 12000:
            raise ValueError("Enter a message of 1–12,000 characters.")
        with session.lock:
            session.pending = None
            if session_id not in self.agents:
                from report_agent.agent.factory import create_report_agent

                factory = self.agent_factory or create_report_agent
                self.agents[session_id] = factory(
                    self.config, session, self.onboarding, self.sources
                )
            session.history.append(
                {"role": "user", "content": display_message or message}
            )
            from langchain_core.callbacks import BaseCallbackHandler

            class ToolProgress(BaseCallbackHandler):
                def on_tool_end(self, output, **kwargs):
                    if progress:
                        progress("Continuing your report…")

                def on_tool_start(self, serialized, input_str, **kwargs):
                    name = serialized.get("name", "")
                    logger.info("Report tool: %s", name)
                    if progress:
                        labels = {
                            "read_file": "Reading report instructions…",
                            "report_context": "Checking your report workspace…",
                            "rendered_examples": "Rendering design examples…",
                            "inspect_source": "Inspecting data columns…",
                            "preview_data": "Checking matching records…",
                            "report_contract": "Preparing the report definition…",
                            "create_draft": "Building your template…",
                            "preview_report": "Rendering your preview…",
                            "propose_report_run": "Preparing parameters for review…",
                        }
                        progress(labels.get(name, "Working on your report…"))

            result = self.agents[session_id].invoke(
                {"messages": [{"role": "user", "content": message}]},
                config={
                    "configurable": {"thread_id": session_id},
                    "recursion_limit": self.config.recursion_limit,
                    "callbacks": [ToolProgress()],
                },
            )
            last = result["messages"][-1]
            logger.info(
                "Report turn: messages=%s finish=%s tokens=%s",
                len(result["messages"]),
                getattr(last, "response_metadata", {}).get("finish_reason"),
                getattr(last, "usage_metadata", None),
            )
            response = last.content
            if isinstance(response, list):
                response = "\n".join(
                    p.get("text", "") for p in response if isinstance(p, dict)
                )
            labels = {ref: name for name, ref in session.candidates.items()}
            labels.update(
                {
                    item["reference"]: item["name"]
                    for item in self.onboarding.store.list()
                }
            )
            labels.update(session.source_labels)
            for reference in (session.draft, session.accepted):
                if reference:
                    labels[reference] = self.onboarding.store.load(reference).name
            response = str(response)
            if not response.strip():
                raise EmptyModelResponse("Model returned no text.")
            if labels:
                # One pass prevents prefix collisions and replacements inside names.
                pattern = "|".join(
                    re.escape(r) for r in sorted(labels, key=len, reverse=True)
                )
                response = re.sub(
                    rf"(?<![\w/-])(?:{pattern})(?![\w/-])",
                    lambda match: labels[match.group()],
                    response,
                )
            if not re.search(r"\bsql\b|show.*quer|inspect.*quer", message, re.I):
                response = re.sub(
                    r"```sql[ \t]*\r?\n.*?```",
                    "",
                    response,
                    flags=re.I | re.S,
                )
            session.history.append({"role": "assistant", "content": response})
            return session

    def upload_sample(self, session_id, path):
        session = self.get_session(session_id)
        with session.lock:
            session.sample = extract_sample(Path(path))
            return session.sample

    def upload_data(self, session_id, path):
        session = self.get_session(session_id)
        path = Path(path)
        if (
            path.suffix.lower() not in {".csv", ".xlsx"}
            or path.stat().st_size > 20 * 1024 * 1024
        ):
            raise ValueError("Upload a CSV or XLSX data file no larger than 20 MiB.")
        if path.suffix.lower() == ".xlsx":
            from report_agent.ingestion.archives import validate_archive

            validate_archive(path)
        name = "upload_" + uuid4().hex
        directory = self.onboarding.store.root / "sources" / name
        directory.mkdir(parents=True)
        destination = directory / ("data" + path.suffix.lower())
        shutil.copy2(path, destination)
        (directory / "source.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "file": destination.name,
                    "filters": {},
                    "original_name": path.name,
                }
            )
        )
        self.sources[name] = FileSource(destination)
        session.source_labels[name] = path.name
        self.source_labels[name] = path.name
        return name
