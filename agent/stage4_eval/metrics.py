from __future__ import annotations

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from agent.models import RepoContext, TestSpec
from agent.stage4_eval.models import MetricResult

EVAL_MODEL = "gpt-4o"

QUICK_METRIC_NAMES = {
    "No Hallucinated Page Methods",
    "Spec Coverage",
}

METRIC_INPUTS = [
    (
        "No Hallucinated Page Methods",
        """
        Check every page-object method or property used by the generated TypeScript test.
        It must exist in the provided page API context. Playwright built-ins and expect()
        are allowed. Raw page.fill, page.click, page.locator, CSS selectors, and invented
        page-object methods are failures unless they are explicitly present in the repo
        context. Score 1.0 for no hallucinations, 0.75 for one minor issue, 0.5 for two
        issues, and 0.0 for three or more.
        """,
        0.75,
    ),
    (
        "Fixture Accuracy",
        """
        Check that fixtures used in test callbacks are available in the provided fixture
        context. Built-in Playwright fixtures such as page, context, browser, and request
        are allowed. Penalize invented custom fixtures.
        """,
        0.85,
    ),
    (
        "Playwright Convention Adherence",
        """
        Check TypeScript Playwright conventions: imports test/expect, async test bodies,
        awaited actions, .spec.ts style, no Python/pytest syntax, and clean test.describe
        organization where useful.
        """,
        0.80,
    ),
    (
        "Spec Coverage",
        """
        Check whether every test case from the input spec is represented by a generated
        test with relevant steps and assertions. Score according to covered cases divided
        by required cases.
        """,
        0.80,
    ),
    (
        "Assertion Strength",
        """
        Evaluate whether assertions verify meaningful business outcomes from the expected
        results, not only generic page visibility or URL changes.
        """,
        0.75,
    ),
    (
        "Flow Order Validation",
        """
        Compare the generated action order to the required steps and navigation knowledge.
        The test should navigate, act, then assert in the correct business sequence.
        """,
        0.75,
    ),
    (
        "Business Rule Compliance",
        """
        Check that the generated test respects domain rules in the knowledge context.
        Penalize invented workflows, invalid users, impossible states, and missing required
        preconditions.
        """,
        0.75,
    ),
]


def evaluate_all_metrics(
    code: str, spec: TestSpec, context: RepoContext, full: bool = False
) -> list[MetricResult]:
    spec_text = spec.model_dump_json(indent=2)
    repo_text = "\n\n".join(
        [
            "Page API:\n" + context.page_api_summary(),
            "Fixtures:\n" + "\n".join(f"- {fixture.name}" for fixture in context.fixtures),
            "Knowledge:\n" + "\n\n".join(context.knowledge.values()),
        ]
    )

    results: list[MetricResult] = []
    metric_inputs = METRIC_INPUTS if full else _quick_metric_inputs()
    for name, criteria, threshold in metric_inputs:
        metric = GEval(
            name=name,
            model=EVAL_MODEL,
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.CONTEXT,
            ],
            criteria=criteria.strip(),
            threshold=threshold,
        )
        test_case = LLMTestCase(input=spec_text, actual_output=code, context=[repo_text])
        try:
            metric.measure(test_case)
            results.append(
                MetricResult(
                    name=name,
                    score=round(metric.score or 0.0, 3),
                    passed=metric.is_successful(),
                    reason=metric.reason or "",
                    issues=[] if metric.is_successful() else [metric.reason or f"{name} failed"],
                )
            )
        except Exception as exc:
            reason = f"{name} could not be evaluated: {type(exc).__name__}: {exc}"
            results.append(
                MetricResult(
                    name=name,
                    score=0.0,
                    passed=False,
                    reason=reason,
                    issues=[reason],
                )
            )
    return results


def _quick_metric_inputs() -> list[tuple[str, str, float]]:
    return [item for item in METRIC_INPUTS if item[0] in QUICK_METRIC_NAMES]
