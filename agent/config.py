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


@dataclass(frozen=True)
class AgentConfig:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    project_root: Path = Path(__file__).resolve().parents[1]
    playwright_root: Path = Path(os.getenv("PLAYWRIGHT_ROOT", "playwright"))
    max_tool_rounds: int = 8

    @classmethod
    def load(cls) -> "AgentConfig":
        cfg = cls()
        if not cfg.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required")
        return cfg

    def playwright_path(self) -> Path:
        if self.playwright_root.is_absolute():
            return self.playwright_root
        return self.project_root / self.playwright_root
