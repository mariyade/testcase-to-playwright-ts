from __future__ import annotations

from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from agent.models import RepoContext, TestSpec
from agent.stage4_eval.models import MetricResult


EVAL_MODEL = "gpt-4o"


def run_llm_metric(name: str, criteria: str, input_text: str, actual_output: str, context: str, threshold: float) -> MetricResult:
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
    test_case = LLMTestCase(input=input_text, actual_output=actual_output, context=[context])
    metric.measure(test_case)
    issues = [] if metric.is_successful() else [metric.reason or f"{name} failed"]
    return MetricResult(
        name=name,
        score=round(metric.score or 0.0, 3),
        passed=metric.is_successful(),
        reason=metric.reason or "",
        issues=issues,
    )


def evaluate_all_metrics(code: str, spec: TestSpec, context: RepoContext) -> list[MetricResult]:
    spec_text = spec.model_dump_json(indent=2)
    repo_text = "\n\n".join([
        "Page API:\n" + context.page_api_summary(),
        "Fixtures:\n" + "\n".join(f"- {f.name}" for f in context.fixtures),
        "Knowledge:\n" + "\n\n".join(context.knowledge.values()),
    ])

    return [
        run_llm_metric(
            "No Hallucinated Page Methods",
            """
            Check every page-object method or property used by the generated TypeScript test.
            It must exist in the provided page API context. Playwright built-ins and expect()
            are allowed. Score 1.0 for no hallucinations, 0.75 for one minor issue,
            0.5 for two issues, and 0.0 for three or more.
            """,
            spec_text,
            code,
            repo_text,
            0.75,
        ),
        run_llm_metric(
            "Fixture Accuracy",
            """
            Check that fixtures used in test callbacks are available in the provided fixture
            context. Built-in Playwright fixtures such as page, context, browser, and request
            are allowed. Penalize invented custom fixtures.
            """,
            spec_text,
            code,
            repo_text,
            0.85,
        ),
        run_llm_metric(
            "Playwright Convention Adherence",
            """
            Check TypeScript Playwright conventions: imports test/expect, async test bodies,
            awaited actions, .spec.ts style, no Python/pytest syntax, and clean test.describe
            organization where useful.
            """,
            spec_text,
            code,
            repo_text,
            0.80,
        ),
        run_llm_metric(
            "Spec Coverage",
            """
            Check whether every test case from the input spec is represented by a generated
            test with relevant steps and assertions. Score according to covered cases divided
            by required cases.
            """,
            spec_text,
            code,
            repo_text,
            0.80,
        ),
        run_llm_metric(
            "Assertion Strength",
            """
            Evaluate whether assertions verify meaningful business outcomes from the expected
            results, not only generic page visibility or URL changes.
            """,
            spec_text,
            code,
            repo_text,
            0.75,
        ),
        run_llm_metric(
            "Flow Order Validation",
            """
            Compare the generated action order to the required steps and navigation knowledge.
            The test should navigate, act, then assert in the correct business sequence.
            """,
            spec_text,
            code,
            repo_text,
            0.75,
        ),
        run_llm_metric(
            "Business Rule Compliance",
            """
            Check that the generated test respects domain rules in the knowledge context.
            Penalize invented workflows, invalid users, impossible states, and missing required
            preconditions.
            """,
            spec_text,
            code,
            repo_text,
            0.75,
        ),
    ]

