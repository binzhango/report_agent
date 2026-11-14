"""Deep Agents supplies skill discovery and checkpointed conversational history."""

from threading import Lock

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemMiddleware
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver

from report_agent.agent.prompt import SYSTEM_PROMPT
from report_agent.agent.tools.reports import build_tools

_PROFILE_LOCK = Lock()
_REGISTERED_MODELS = set()


def initialize_harness(model_name):
    """Register global framework policy once per model, including direct API use."""
    with _PROFILE_LOCK:
        if model_name in _REGISTERED_MODELS:
            return
        register_harness_profile(
            f"openai:{model_name}",
            HarnessProfile(
                excluded_tools=frozenset(
                    {"task", "execute", "write_file", "edit_file"}
                ),
                general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
            ),
        )
        _REGISTERED_MODELS.add(model_name)


def create_report_agent(config, session, onboarding, sources, *, model=None):
    initialize_harness(config.model)
    if model is None:
        model = ChatOpenAI(
            model=config.model,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            max_tokens=config.max_output_tokens,
            max_retries=2,
            temperature=0,
            streaming=True,
            use_responses_api=False,
        )
    backend = FilesystemBackend(root_dir=str(config.skills_root), virtual_mode=True)
    return create_deep_agent(
        model=model,
        backend=backend,
        skills=["/"],
        tools=build_tools(session, onboarding, sources),
        system_prompt=(
            SYSTEM_PROMPT + f"\nReasoning strength: {config.reasoning_strength}"
            if config.reasoning_strength
            else SYSTEM_PROMPT
        ),
        subagents=[],
        checkpointer=InMemorySaver(),
        middleware=[
            FilesystemMiddleware(
                backend=backend, tools=["ls", "read_file", "glob", "grep"]
            )
        ],
    )
