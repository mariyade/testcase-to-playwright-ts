# AI-powered Test Generation Pipeline for Playwright

An AI-powered automation framework that converts Jira tickets, GitHub issues or free-text requirements into production-ready Playwright TypeScript tests, including end-to-end, API, visual regression and smoke tests.

## Background

This project investigates how Retrieval-Augmented Generation (RAG) can be used to generate grounded Playwright automation from software requirements.

Large language models can generate Playwright tests well but they frequently hallucinate page object methods, fixtures, selectors, and business workflows. This project explores whether retrieving project-specific context before generation can significantly improve the quality and reliability of AI-generated test automation.

The agent:

- parses Jira, GitHub or text test requirements into a structured `TestSpec`
- retrieves the Playwright repo page objects, fixtures, existing tests and project knowledge
- generates Playwright TypeScript tests through a GPT tool loop
- evaluates the generated tests against multiple LLM quality metrics
- regenerates or accepts tests based on the evaluation results


## Table of Contents

- [Background](#background)
- [Layout](#layout)
- [Technology](#technology)
- [Quick Start](#quick-start)
- [Example Workflow](#example-workflow)
- [Demo Target](#demo-target)
- [Evaluation](#evaluation)
- [Regression Suites](#regression-suites)

## Layout

```text
agent/
├── stage1_ticket_parser/
├── stage2_context_retrieval/
├── stage3_generator/
├── stage4_eval/
├── stage5_runner/
└── knowledge/

playwright/
├── pages/
├── fixtures/
├── tests/
│   └── generated/
└── playwright.config.ts
```

## Technology

**AI**
- OpenAI GPT
- Retrieval-Augmented Generation (RAG)
- DeepEval

**Backend**
- Python
- Pydantic
- ChromaDB
- Sentence Transformers

**Test Automation**
- Playwright
- TypeScript
- Node.js

## Quick Start

```bash
cd testcase-to-playwright-ts
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For Playwright tests:

```bash
cd playwright
npm install
npx playwright install
```

## Example Workflow

Generate Playwright tests directly from a user story from a text file:

```bash
.venv/bin/python -m agent.cli \
  --text test_specs/text/contact_form_user_story.txt \
  --save-spec artifacts/stage1/contact_form_user_story_spec.json
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

For multiple Jira tickets, add multiple Jira ticket URLs:

```text
test_specs/jira/tickets.txt
```

Then run the loop script. For Stage 1 parsing only:

```bash
bash scripts/run_jira_tickets.sh --stage1-only
```

For full test generation and evaluation:

```bash
bash scripts/run_jira_tickets.sh
```

Stage 4 uses a quick two-metric evaluation by default to reduce OpenAI rate-limit
pressure. Run the full metric suite only when needed:

```bash
bash scripts/run_jira_tickets.sh --full-eval
```

For full test generation without Stage 4 LLM evaluation:

```bash
bash scripts/run_jira_tickets.sh --skip-eval
```

For multiple GitHub issues, add one URL per line:

```text
test_specs/github/issues.txt
```

Then run Stage 1 parsing only:

```bash
bash scripts/run_github_issues.sh --stage1-only
```

Or full generation and evaluation:

```bash
bash scripts/run_github_issues.sh
```

Use `--stage1-only` to inspect the normalized `TestSpec` without running
generation. Use `--save-spec` to persist the Stage 1 JSON artifact.

For private Jira URLs, set `JIRA_EMAIL` and `JIRA_API_TOKEN`:

```bash
export JIRA_EMAIL="you@example.com"
export JIRA_API_TOKEN="your-api-token"
```

For private GitHub issues or higher API limits, set `GITHUB_TOKEN`.

Free-text and HTML sources use the Stage 1 QA extraction prompt and require
`OPENAI_API_KEY`.

## Demo Target

The default demo target is Restful Booker Platform:

```text
UI  -> https://automationintesting.online/
API -> https://automationintesting.online/api
```

Generated specs are written to:

```text
playwright/tests/generated/e2e/
playwright/tests/generated/visual/
playwright/tests/generated/api/
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
