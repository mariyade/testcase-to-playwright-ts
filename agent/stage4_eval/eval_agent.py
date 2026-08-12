from __future__ import annotations

from pathlib import Path

from agent.models import RepoContext, TestSpec
from agent.stage4_eval.metrics import evaluate_all_metrics
from agent.stage4_eval.models import EvalReport


# Runtime Stage 4 wrapper used by the CLI after Stage 3 writes generated specs.
class Stage4EvalAgent:
    # Evaluate one generated spec file against the Stage 1 spec and Stage 2 context.
    # Missing files become report issues instead of crashing the CLI.
    def evaluate(
        self, filepath: str | Path, spec: TestSpec, context: RepoContext, full: bool = False
    ) -> EvalReport:
        path = Path(filepath)
        report = EvalReport(filepath=str(path))

        if not path.exists():
            report.issues.append(f"Generated file not found: {path}")
            return report

        code = path.read_text(encoding="utf-8")
        report.metrics = evaluate_all_metrics(code, spec, context, full=full)
        return report.compute()
