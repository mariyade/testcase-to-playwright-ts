from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# One TypeScript file produced by Stage 3, with its final safe path.
@dataclass
class GeneratedFile:
    path: Path
    code: str


# Result object returned by Stage3GeneratorAgent to the CLI and eval helpers.
@dataclass
class GenerationResult:
    success: bool
    code: str = ""
    filepath: Path | None = None
    files: list[GeneratedFile] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    error: str = ""
