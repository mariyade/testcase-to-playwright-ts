from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None


if load_dotenv:
    load_dotenv()


DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"


@dataclass(frozen=True)
class AgentConfig:
    openai_api_key: str = os.getenv("AGENT_OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    openai_base_url: str = os.getenv("AGENT_OPENAI_BASE_URL", os.getenv("OPENAI_BASE_URL", ""))
    openai_model: str = os.getenv(
        "AGENT_OPENAI_MODEL", os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    )
    deepeval_model: str = os.getenv(
        "DEEPEVAL_MODEL", os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    )
    project_root: Path = Path(__file__).resolve().parents[1]
    playwright_root: Path = Path(os.getenv("PLAYWRIGHT_ROOT", "playwright"))
    max_tool_rounds: int = 8

    @classmethod
    def load(cls) -> AgentConfig:
        cfg = cls()
        if not cfg.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required")
        return cfg

    def playwright_path(self) -> Path:
        if self.playwright_root.is_absolute():
            return self.playwright_root
        return self.project_root / self.playwright_root

    def token_limit_kwargs(self, value: int) -> dict[str, int]:
        if self.openai_base_url:
            return {"max_tokens": value}
        return {"max_completion_tokens": value}

    @classmethod
    def has_agent_llm_config(cls) -> bool:
        return bool(cls().openai_api_key)
