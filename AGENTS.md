# Repository Instructions

This repository contains a Python-controlled agent that parses Jira, GitHub, or text
requirements, retrieves local Playwright TypeScript context, generates `.spec.ts`
files, evaluates them, and can run Playwright.

## Scope

- Python agent code lives under `agent/`.
- Playwright TypeScript code lives under `playwright/`.
- Human-authored requirements belong under `test_specs/` or `artifacts/stage1/`.
- Generated and runtime outputs belong under `artifacts/`, `playwright/tests/generated/`,
  or ignored Playwright report directories.
- Agent knowledge consumed by the generator belongs under `agent/knowledge/`.

## Quality Gates

Run the relevant checks before finishing changes:

```bash
.venv/bin/ruff check agent
.venv/bin/ruff format --check agent
.venv/bin/python -m compileall agent
npm --prefix playwright run lint
npm --prefix playwright run typecheck
npm --prefix playwright run test:list
```

For the full local hook suite:

```bash
.venv/bin/pre-commit run --all-files
```

Run browser E2E only when network/browser access is appropriate:

```bash
npm --prefix playwright test
```

## Python Standards

- Follow Ruff rules from `pyproject.toml`.
- Keep parser inputs limited to Jira, GitHub, and text sources.
- Prefer typed models from `agent/models.py` over unstructured dictionaries.
- Keep generated artifacts out of source modules.

## Playwright Standards

- Generated specs live in `playwright/tests/generated/*.spec.ts`.
- From generated specs, import fixtures with:

```ts
import { expect, test } from '../../fixtures/test';
```

- Prefer page objects from `playwright/pages/`.
- Prefer fixtures from `playwright/fixtures/test.ts`.
- Use stable Playwright locators such as `getByRole`, `getByLabel`, and `getByTestId`.
- Avoid hard waits, XPath, and layout-dependent selectors.
- Keep API response JSON typed or validated before using it.

## QA Expectations

- Test observable behaviour rather than implementation details.
- Use acceptance criteria and `agent/knowledge/*.yaml` as generation context.
- Do not invent credentials, selectors, routes, screenshots, console errors, or test results.
- Skip admin or signed-in user flows unless credentials and supporting page objects exist.
- When reporting issues, include scope, evidence, expected result, actual result, and risk.

## Git

- Do not push unless the user explicitly asks.
- Use Conventional Commit messages, for example:

```bash
git commit -m "fix: remove excel input path"
git commit -m "ci: add lint gates"
git commit -m "docs: clarify qa strategy"
```
