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
    if target.is_absolute():
        target_arg = str(target.relative_to(root))
    else:
        target_arg = str(target)

    command = ["npx", "playwright", "test", target_arg]
    completed = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return RunResult(command, completed.returncode, completed.stdout, completed.stderr)


def list_playwright_tests(playwright_root: str | Path) -> RunResult:
    command = ["npx", "playwright", "test", "--list"]
    completed = subprocess.run(
        command,
        cwd=Path(playwright_root),
        capture_output=True,
        text=True,
        check=False,
    )
    return RunResult(command, completed.returncode, completed.stdout, completed.stderr)

