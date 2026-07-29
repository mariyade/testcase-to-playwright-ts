from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def run_playwright(playwright_root: str | Path, spec_file: str | Path) -> RunResult:
    root = Path(playwright_root)
    target = Path(spec_file)
    target_arg = str(target.relative_to(root)) if target.is_absolute() else str(target)
    return _run_playwright_command(root, ["npx", "playwright", "test", target_arg])


def list_playwright_tests(playwright_root: str | Path) -> RunResult:
    return _run_playwright_command(Path(playwright_root), ["npx", "playwright", "test", "--list"])


def _run_playwright_command(root: Path, command: list[str]) -> RunResult:
    completed = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return RunResult(command, completed.returncode, completed.stdout, completed.stderr)
