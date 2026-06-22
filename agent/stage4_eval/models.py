from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Recommendation(str, Enum):
    ACCEPT = "accept"
    REGENERATE = "regenerate"
    ESCALATE = "escalate"


@dataclass
class MetricResult:
    name: str
    score: float
    passed: bool
    reason: str = ""
    issues: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    filepath: str
    generated_at: datetime = field(default_factory=datetime.utcnow)
    metrics: list[MetricResult] = field(default_factory=list)
    overall_score: float = 0.0
    passed: bool = False
    recommendation: Recommendation = Recommendation.ESCALATE
    issues: list[str] = field(default_factory=list)

    accept_threshold: float = 0.72
    regenerate_threshold: float = 0.52

    def compute(self) -> "EvalReport":
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

