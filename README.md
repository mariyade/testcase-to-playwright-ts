# AI-powered Test Generation Pipeline for Playwright

An AI-powered test automation pipeline that converts Jira tickets, GitHub issues, and free-text requirements into Playwright TypeScript tests.

This project uses RAG and LLMs to generate Playwright TypeScript tests from software requirements using project-specific repository context.

## Table of Contents

- [Overview](#overview)
- [Technology](#technology)
- [Quick Start](#quick-start)
- [Running Locally](#running-locally)
- [Supported Requirements](#supported-requirements)
- [RAG Context Retrieval](#rag-context-retrieval)
- [Test Generation](#test-generation)
- [Evaluation](#evaluation)
- [Regression Suites](#regression-suites)
- [Demo Application](#demo-application)
- [Security](#security)

## Overview

The pipeline consists of the following stages:

- Stage 1: parses requirements from Jira tickets, GitHub issues, or free text. It validates the input using input guardrails and converts the requirement into a structured `TestSpec` containing one or more test cases.
- Stage 2: retrieves relevant page objects, fixtures, existing tests, and project knowledge from the vector store.
- Stage 3: generates Playwright TypeScript tests using the `TestSpec` and retrieved repository context. It also applies an output guardrail by validating generated code against repository contracts before saving files.
- Stage 4: evaluates generated tests using DeepEval and custom LLM-based quality metrics, then returns a quality score and recommendation.

## Technology

- **AI**: OpenAI GPT, Ollama, DeepEval
- **Backend**: Python, Pydantic
- **RAG / Vector Search**: ChromaDB, Sentence Transformers
- **Test Automation**: Playwright, TypeScript

## Quick Start

```bash
cd testcase-to-playwright-ts
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For Playwright tests:

```bash
cd playwright
npm install
npx playwright install
```

## Running Locally

Install the Python dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Install Playwright:

```bash
cd playwright
npm install
npx playwright install
```

The generation stages can run against OpenAI models or local models through
Ollama.

For example:

```bash
ollama serve
ollama pull qwen2.5-coder:14b

export AGENT_OPENAI_BASE_URL="http://localhost:11434/v1"
export AGENT_OPENAI_API_KEY="ollama"
export AGENT_OPENAI_MODEL="qwen2.5-coder:14b"
```

To keep Stage 4/DeepEval on OpenAI while Stage 1 and Stage 3 use Ollama:

```bash
unset OPENAI_BASE_URL
export OPENAI_API_KEY="YOUR_REAL_OPENAI_KEY"
export DEEPEVAL_MODEL="gpt-5.4-mini"
```

`AGENT_OPENAI_*` controls Stage 1 and Stage 3. `DEEPEVAL_MODEL` controls
Stage 4 and the DeepEval RAG tests.

## Supported Requirements

Tests can be generated from:

- Jira tickets
- GitHub issues
- local text requirements

Example:

```bash
.venv/bin/python -m agent.cli \
  --text test_specs/text/contact_form_user_story.txt \
  --save-spec artifacts/stage1/contact_form_user_story_spec.json
```

Use `--stage1-only` to inspect the normalized `TestSpec` without generating
tests:

```bash
.venv/bin/python -m agent.cli \
  --text test_specs/text/contact_form_user_story.txt \
  --save-spec artifacts/stage1/contact_form_user_story_spec.json \
  --stage1-only
```

## RAG Context Retrieval

Before generating tests, build the searchable Stage 2 index from the local
Playwright repository:

```bash
python3 -m agent.cli --build-index
```

The index contains Playwright page objects, fixtures, existing Playwright tests and project-specific test knowledge.


*Rebuild the index whenever changes are made to files that Stage 2 should know
about. This is important because the generator reads repository context from
the saved index, not directly from every file on each run. Rebuild after
changing page objects, fixtures, existing tests, or files under `agent/knowledge/`.*

## Test Generation

Generated tests are written to:

```text
playwright/tests/generated/
```

The generator uses repository contracts and retrieved context to constrain test
generation.

Validation checks include:

- page-object methods exist, or proposed methods are clearly marked for review
- generated files map back to the expected test specification
- unsupported debug code is rejected
- generated files are written only to the expected test directory

Run generation from a local text requirement:

```bash
.venv/bin/python -m agent.cli \
  --text test_specs/text/contact_form_user_story.txt \
  --save-spec artifacts/stage1/contact_form_user_story_spec.json
```

Skip Stage 4 LLM evaluation during quick local experiments:

```bash
.venv/bin/python -m agent.cli \
  --text test_specs/text/contact_form_user_story.txt \
  --save-spec artifacts/stage1/contact_form_user_story_spec.json \
  --skip-eval
```

For private Jira URLs, set `JIRA_EMAIL` and `JIRA_API_TOKEN`:

```bash
export JIRA_EMAIL="you@example.com"
export JIRA_API_TOKEN="your-api-token"
```

Run one Jira ticket URL:

```bash
.venv/bin/python -m agent.cli \
  --jira "https://your-domain.atlassian.net/rest/api/3/issue/KEY-123" \
  --save-spec artifacts/stage1/KEY-123_spec.json
```

Run one GitHub issue URL:

```bash
.venv/bin/python -m agent.cli \
  --github "https://github.com/owner/repo/issues/123" \
  --save-spec artifacts/stage1/github_123_spec.json
```

## Evaluation

Generated tests are evaluated using multiple LLM-based metrics, including:

- Page Object Hallucination
- Fixture Accuracy
- Playwright Convention Adherence
- Specification Coverage
- Assertion Quality
- Flow Order Validation
- Business Rule Compliance

Retrieval quality is evaluated separately using DeepEval to measure context relevance and generation faithfulness.

Run the RAG/DeepEval tests with:

```bash
.venv/bin/python -m pytest agent/stage4_eval/test_rag_deepeval.py -m evaluation
```

Run Stage 4 against an existing generated file without regenerating tests:

```bash
.venv/bin/python -m agent.cli \
  --eval-file playwright/tests/generated/e2e/guest_sends_contact_message.spec.ts \
  --spec artifacts/stage1/room_booking_user_story_spec.json
```

Evaluation reports are written under:

```text
evaluation_results/
```

RAG datasets are JSONL golden files under:

```text
agent/stage4_eval/datasets/
```

Each line is a DeepEval `Golden`, for example an `input`, `expected_output`,
and optional `additional_metadata`. These files do not store Playwright
`.spec.ts` files directly. A golden can reference a generated spec path in
`additional_metadata.generated_file`, and the eval helper will read that file
when the test runs.

To create portfolio-safe synthetic goldens from sanitized documents, use the
optional DeepEval Synthesizer helper:

```bash
.venv/bin/python -m agent.stage4_eval.synthesize_dataset \
  agent/stage4_eval/synthetic_sources/portfolio_product_context.md \
  --output-dir agent/stage4_eval/datasets/synthetic
```

This calls DeepEval's `EvaluationDataset.save_as(file_type="jsonl", ...)`.
By default it saves goldens only. Add `--include-test-cases` if you also want
DeepEval test cases saved and your installed DeepEval version supports it.

## Regression Suites

Run regression automation in this order:

```bash
npm --prefix playwright run test:smoke
npm --prefix playwright run test:regression:visual
npm --prefix playwright run test:regression:e2e
```

Or run the ordered suite:

```bash
npm --prefix playwright run test:regression
```

Visual regression covers the main responsive breakpoints:

```text
desktop -> 1440x900
tablet  -> 768x1024
mobile  -> 390x844
```

Animations and transitions are disabled during screenshot capture to produce deterministic visual baselines.

Keep screenshot baselines on one OS. In CI, prefer Docker/Linux so font
rendering does not vary between macOS, Windows, and Linux.

## Demo Application

The default test target is Restful Booker Platform:

```text
UI  -> https://automationintesting.online/
API -> https://automationintesting.online/api
```

The project generates and evaluates Playwright tests against this application.

## Security

Input requirements are validated before being passed to the LLM.

The pipeline includes:

- prompt-injection detection
- secret detection
- optional PII detection using Presidio
- controlled output paths for generated test files
- repository-contract validation before generated tests are accepted

Optional PII detection can be enabled with:

```bash
export AGENT_ENABLE_PII_GUARD=true
```

Install Presidio first if you enable this mode:

```bash
pip install presidio-analyzer
```
