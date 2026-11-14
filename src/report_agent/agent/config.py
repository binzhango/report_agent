"""Explicit model configuration; no credentials in report bundles or chat state."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentConfig:
    model: str
    skills_root: Path
    base_url: str | None = None
    recursion_limit: int = 80
    timeout_seconds: float = 120
    max_output_tokens: int = 4096
    reasoning_strength: str | None = None

    @classmethod
    def from_environment(cls):
        model = os.environ.get("REPORT_AGENT_MODEL", "").strip()
        if not model:
            raise ValueError("Set REPORT_AGENT_MODEL to your tool-capable model name.")
        if not os.environ.get("OPENAI_API_KEY"):
            raise ValueError("Set OPENAI_API_KEY for your OpenAI-compatible endpoint.")
        skills = Path(os.environ.get("REPORT_AGENT_SKILLS", ".agents/skills")).resolve()
        if not list(skills.glob("*/SKILL.md")):
            raise ValueError(
                "Set REPORT_AGENT_SKILLS to the deployed .agents/skills directory."
            )
        timeout = float(os.environ.get("REPORT_AGENT_TIMEOUT", "120"))
        tokens = int(os.environ.get("REPORT_AGENT_MAX_TOKENS", "4096"))
        strength = os.environ.get("REPORT_AGENT_REASONING_STRENGTH") or None
        if strength not in {None, "low", "medium", "high", "xhigh"}:
            raise ValueError(
                "REPORT_AGENT_REASONING_STRENGTH must be low/medium/high/xhigh."
            )
        if not 0 < timeout <= 600 or not 256 <= tokens <= 32768:
            raise ValueError(
                "Use a timeout of 1–600 seconds and 256–32768 output tokens."
            )
        return cls(
            model=model,
            skills_root=skills,
            base_url=os.environ.get("OPENAI_BASE_URL"),
            timeout_seconds=timeout,
            max_output_tokens=tokens,
            reasoning_strength=strength,
        )
