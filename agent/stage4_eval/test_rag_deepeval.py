# ruff: noqa: E402
from __future__ import annotations

import pytest

from agent.config import AgentConfig
from agent.stage4_eval.helpers import generated_output, load_json_rows, retrieved_context

# DeepEval is optional, so these tests are skipped unless the package is installed.
deepeval = pytest.importorskip("deepeval")
deepeval_dataset = pytest.importorskip("deepeval.dataset")
deepeval_evaluate = pytest.importorskip("deepeval.evaluate")
deepeval_metrics = pytest.importorskip("deepeval.metrics")
deepeval_test_case = pytest.importorskip("deepeval.test_case")

assert_test = deepeval.assert_test
evaluate = deepeval.evaluate
CacheConfig = deepeval_evaluate.CacheConfig
DisplayConfig = deepeval_evaluate.DisplayConfig
ErrorConfig = deepeval_evaluate.ErrorConfig
EvaluationDataset = deepeval_dataset.EvaluationDataset
Golden = deepeval_dataset.Golden
AnswerRelevancyMetric = deepeval_metrics.AnswerRelevancyMetric
ContextualPrecisionMetric = deepeval_metrics.ContextualPrecisionMetric
ContextualRecallMetric = deepeval_metrics.ContextualRecallMetric
ContextualRelevancyMetric = deepeval_metrics.ContextualRelevancyMetric
FaithfulnessMetric = deepeval_metrics.FaithfulnessMetric
LLMTestCase = deepeval_test_case.LLMTestCase

pytestmark = pytest.mark.evaluation


# Build a DeepEval dataset from this stage's JSONL golden files.
def _dataset(relative_path: str) -> EvaluationDataset:
    rows = load_json_rows(relative_path)
    return EvaluationDataset(goldens=[Golden(**row) for row in rows])


# Golden datasets are loaded once so pytest can parametrize individual examples.
RAG_RETRIEVAL_DATASET = _dataset("datasets/rag_retrieval_goldens.jsonl")
RAG_GENERATION_DATASET = _dataset("datasets/rag_generation_goldens.jsonl")

# Keep DeepEval model choice centralized through AgentConfig/DEEPEVAL_MODEL.
DEEPEVAL_MODEL = AgentConfig().deepeval_model


# Score whether retrieval returns context relevant to each golden requirement.
@pytest.mark.parametrize("golden", RAG_RETRIEVAL_DATASET.goldens)
def test_rag_retrieval_metrics(golden):
    assert_test(
        LLMTestCase(
            input=golden.input,
            expected_output=golden.expected_output,
            retrieval_context=retrieved_context(golden.input),
        ),
        [
            ContextualRelevancyMetric(threshold=0.5, model=DEEPEVAL_MODEL),
            ContextualPrecisionMetric(threshold=0.5, model=DEEPEVAL_MODEL),
            ContextualRecallMetric(threshold=0.5, model=DEEPEVAL_MODEL),
        ],
    )


# Score whether generated output is faithful and relevant to retrieved context.
@pytest.mark.parametrize("golden", RAG_GENERATION_DATASET.goldens)
def test_rag_generation_metrics(golden):
    metadata = golden.additional_metadata or {}
    result = generated_output(metadata)
    assert_test(
        LLMTestCase(
            input=golden.input,
            actual_output=result,
            expected_output=golden.expected_output,
            retrieval_context=retrieved_context(metadata["context_query"]),
        ),
        [
            FaithfulnessMetric(threshold=0.5, model=DEEPEVAL_MODEL),
            AnswerRelevancyMetric(threshold=0.5, model=DEEPEVAL_MODEL),
        ],
    )


# Run retrieval goldens through DeepEval's batch API with result caching enabled.
def test_rag_retrieval_batch_evaluate_with_cache():
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
            ContextualRelevancyMetric(threshold=0.5, model=DEEPEVAL_MODEL),
            ContextualPrecisionMetric(threshold=0.5, model=DEEPEVAL_MODEL),
            ContextualRecallMetric(threshold=0.5, model=DEEPEVAL_MODEL),
        ],
        cache_config=CacheConfig(write_cache=True, use_cache=True),
        error_config=ErrorConfig(ignore_errors=False),
        display_config=DisplayConfig(
            print_results=True,
            results_folder="evaluation_results/deepeval",
        ),
    )

    failed = [test for test in result.test_results if not test.success]
    assert not failed, [test.name or test.input for test in failed]
