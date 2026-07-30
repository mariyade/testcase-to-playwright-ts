# ruff: noqa: E402
from __future__ import annotations

import pytest

from agent.evals.helpers import generated_output, load_json_rows, retrieved_context

deepeval = pytest.importorskip("deepeval")
deepeval_metrics = pytest.importorskip("deepeval.metrics")
deepeval_test_case = pytest.importorskip("deepeval.test_case")

evaluate = deepeval.evaluate
AnswerRelevancyMetric = deepeval_metrics.AnswerRelevancyMetric
ContextualPrecisionMetric = deepeval_metrics.ContextualPrecisionMetric
ContextualRecallMetric = deepeval_metrics.ContextualRecallMetric
ContextualRelevancyMetric = deepeval_metrics.ContextualRelevancyMetric
FaithfulnessMetric = deepeval_metrics.FaithfulnessMetric
LLMTestCase = deepeval_test_case.LLMTestCase

pytestmark = pytest.mark.evaluation


def test_stage2_rag_retrieval_batch():
    rows = load_json_rows("datasets/rag_retrieval_goldens.jsonl")
    test_cases = [
        LLMTestCase(
            input=row["input"],
            expected_output=row["expected_output"],
            retrieval_context=retrieved_context(row["input"]),
        )
        for row in rows
    ]

    result = evaluate(
        test_cases=test_cases,
        metrics=[
            ContextualRelevancyMetric(threshold=0.5),
            ContextualPrecisionMetric(threshold=0.5),
            ContextualRecallMetric(threshold=0.5),
        ],
    )

    failed = [test for test in result.test_results if not test.success]
    assert not failed, [test.name or test.input for test in failed]


def test_stage3_rag_generation_batch():
    rows = load_json_rows("datasets/rag_generation_goldens.jsonl")
    test_cases = [
        LLMTestCase(
            input=row["input"],
            actual_output=generated_output(row.get("additional_metadata", {})),
            expected_output=row["expected_output"],
            retrieval_context=retrieved_context(row["additional_metadata"]["context_query"]),
        )
        for row in rows
    ]

    result = evaluate(
        test_cases=test_cases,
        metrics=[
            FaithfulnessMetric(threshold=0.5),
            AnswerRelevancyMetric(threshold=0.5),
        ],
    )

    failed = [test for test in result.test_results if not test.success]
    assert not failed, [test.name or test.input for test in failed]
