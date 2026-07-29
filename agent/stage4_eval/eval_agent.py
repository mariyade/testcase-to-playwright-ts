from __future__ import annotations

from pathlib import Path

from agent.models import RepoContext, TestSpec
from agent.stage4_eval.metrics import evaluate_all_metrics
from agent.stage4_eval.models import EvalReport


class Stage4EvalAgent:
    def evaluate(self, filepath: str | Path, spec: TestSpec, context: RepoContext) -> EvalReport:
        path = Path(filepath)
        report = EvalReport(filepath=str(path))

        if not path.exists():
            report.issues.append(f"Generated file not found: {path}")
            return report

        code = path.read_text(encoding="utf-8")
        report.metrics = evaluate_all_metrics(code, spec, context)
        return report.compute()
