# Testcase to Playwright TS

Python AI automation agent that reads test specifications, retrieves TypeScript
Playwright context, generates `.spec.ts` tests, evaluates them with LLM-centered
metrics, and can run Playwright.

This is an original scaffold for a Python-controlled, TypeScript-Playwright
test generation framework.

## Table of Contents

- [Pipeline](#pipeline)
- [Layout](#layout)
- [Quick Start](#quick-start)
- [Input Sources](#input-sources)
- [Demo Target](#demo-target)
- [Stage 2 Retrieval](#stage-2-retrieval)
- [Generate and Evaluate Tests](#generate-and-evaluate-tests)
- [Run Generated Playwright Tests](#run-generated-playwright-tests)

## Pipeline

1. Parse Jira, GitHub, or text test specifications into a normalized `TestSpec`.
2. Scan the Playwright repo for page objects, fixtures, existing specs, and rules.
3. Generate TypeScript Playwright tests through a GPT tool loop.
4. Evaluate generated tests with LLM metrics and targeted static evidence.
5. Regenerate, accept, or escalate based on the evaluation report.
6. Run `npx playwright test`.

## Layout

```text
agent/
  models.py
  config.py
  stage1_ticket_parser/
    parser.py
    jira.py
    github.py
    text.py
    llm.py
  stage2_context_retrieval/
    chunker.py
    indexer.py
    retriever.py
  stage3_generator/
  stage4_eval/
  stage5_runner/
  knowledge/

playwright/
  package.json
  playwright.config.ts
  pages/
  fixtures/
  tests/generated/
```

Knowledge files are written consistently as YAML so rules, roles, page mappings,
navigation flows, and generation standards can all be scanned into the agent
context in one predictable format.

## Quick Start

```bash
cd testcase-to-playwright-ts
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For Playwright dependencies:

```bash
cd playwright
npm install
npx playwright install
```

## Input Sources

Stage 1 can read ticket specifications from Jira JSON, GitHub issues, or text/URL sources:

```bash
python -m agent.cli --jira path/to/jira-issue.json
python -m agent.cli --jira path/to/jira-issue.json --stage1-only --save-spec artifacts/stage1/jira_issue_spec.json
python -m agent.cli --jira "https://your-domain.atlassian.net/rest/api/3/issue/KEY-123" --stage1-only --save-spec artifacts/stage1/jira_KEY-123.json
python -m agent.cli --github https://github.com/midnightntwrk/midnight-indexer/issues/1253 --stage1-only
python -m agent.cli --text artifacts/stage1/room_booking_user_story.txt
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

The project includes a sample room-booking story:

```bash
python -m agent.cli \
  --text artifacts/stage1/room_booking_user_story.txt \
  --stage1-only \
  --save-spec artifacts/stage1/room_booking_user_story_spec.json
```

Run retrieval only:

```bash
python -m agent.cli \
  --text artifacts/stage1/room_booking_user_story.txt \
  --retrieve-context
```

Run the checked-in UI plus API example:

```bash
npm --prefix playwright test tests/examples/booking.spec.ts
```

## Stage 2 Retrieval

Stage 2 builds a grounded local context index from the Playwright project before
test generation. It indexes three collections:

```text
code_index  -> page objects and fixtures
test_index  -> existing example specs
know_index  -> YAML knowledge files
```

Build or refresh the index after changing page objects, fixtures, tests, or
knowledge:

```bash
python -m agent.cli --build-index
```

Search the index while debugging:

```bash
python -m agent.cli --search-index "room booking API confirmation guest dates"
```

Parse Stage 1 and retrieve Stage 2 context without generating code:

```bash
python -m agent.cli \
  --text artifacts/stage1/room_booking_user_story.txt \
  --retrieve-context
```

The current implementation uses deterministic local chunking plus real embedding
retrieval with `sentence-transformers` and ChromaDB:

```text
embedding model -> all-MiniLM-L6-v2
vector store    -> agent/vector_store/chroma/
debug fallback  -> agent/vector_store/stage2_index.json
```

If ChromaDB, sentence-transformers, or the local embedding model cache is not
available, Stage 2 falls back to deterministic lexical search over
`stage2_index.json` instead of breaking the pipeline.

## Generate and Evaluate Tests

Run the full pipeline from a source spec:

```bash
export OPENAI_API_KEY="your-api-key"

python -m agent.cli \
  --text artifacts/stage1/room_booking_user_story.txt
```

That runs Stage 1 parsing, Stage 2 retrieval, Stage 3 TypeScript generation,
and Stage 4 evaluation. Generated specs are written to:

```text
playwright/tests/generated/
```

Use `--dry-run` to print the generated TypeScript without writing the spec file.

## Run Generated Playwright Tests

Run all generated tests:

```bash
npm --prefix playwright test tests/generated
```

Run the checked-in booking example:

```bash
npm --prefix playwright test tests/examples/booking.spec.ts
```

Run with the browser visible:

```bash
npm --prefix playwright test tests/examples/booking.spec.ts -- --headed
```
