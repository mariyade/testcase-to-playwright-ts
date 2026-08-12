from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


# Final action suggested by Stage 4 after metric aggregation.
class Recommendation(StrEnum):
    ACCEPT = "accept"
    REGENERATE = "regenerate"
    ESCALATE = "escalate"


# One DeepEval metric result normalized into the agent's report format.
@dataclass
class MetricResult:
    name: str
    score: float
    passed: bool
    reason: str = ""
    issues: list[str] = field(default_factory=list)


# Saved Stage 4 report for one generated Playwright spec file.
@dataclass
class EvalReport:
    filepath: str
    generated_at: datetime = field(default_factory=datetime.utcnow)
    metrics: list[MetricResult] = field(default_factory=list)
    overall_score: float = 0.0
    passed: bool = False
    recommendation: Recommendation = Recommendation.ESCALATE
    issues: list[str] = field(default_factory=list)

    # Thresholds define when generated code is accepted, regenerated, or escalated.
    accept_threshold: float = 0.72
    regenerate_threshold: float = 0.52

    # Convert the report into JSON-safe values for saved evaluation artifacts.
    def to_json_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["generated_at"] = self.generated_at.isoformat()
        data["recommendation"] = self.recommendation.value
        return data

    # Aggregate metric scores into the final accept/regenerate/escalate decision.
    def compute(self) -> EvalReport:
        weights = {
            "No Hallucinated Page Methods": 0.18,
            "Fixture Accuracy": 0.12,
            "Playwright Convention Adherence": 0.10,
            "Spec Coverage": 0.22,
            "Assertion Strength": 0.15,
            "Flow Order Validation": 0.13,
            "Business Rule Compliance": 0.10,
        }
        total = 0.0
        weight_total = 0.0
        for metric in self.metrics:
            weight = weights.get(metric.name, 0.10)
            total += metric.score * weight
            weight_total += weight
            self.issues.extend(metric.issues)

        self.overall_score = round(total / weight_total if weight_total else 0.0, 3)
        self.passed = self.overall_score >= self.accept_threshold
        if self.passed:
            self.recommendation = Recommendation.ACCEPT
        elif self.overall_score >= self.regenerate_threshold:
            self.recommendation = Recommendation.REGENERATE
        else:
            self.recommendation = Recommendation.ESCALATE
        return self
