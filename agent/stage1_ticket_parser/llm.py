from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from openai import OpenAI

from agent.config import AgentConfig
from agent.models import InputSource, TestSpec
from agent.stage1_ticket_parser.input_guardrails import validate_stage1_input

SYSTEM_PROMPT = """
You are Stage 1 of a QA pipeline.

Your job is to transform a requirement, Jira ticket, GitHub issue,
or free-text note into one normalized
TestSpec JSON document for downstream Playwright test generation.

Your responsibility is to faithfully extract and structure the business intent,
not to invent product behaviour or implementation details.

Think like an experienced QA analyst whose responsibility is to identify
testable business behaviour, not implementation details.

Before producing the output, internally identify:

- what feature or behaviour is being requested
- what problem the feature solves
- what the user is trying to accomplish
- what conditions define success
- what explicit acceptance criteria exist
- what business rules or validation rules exist
- what observable behaviours can be verified

Do not output this reasoning.

Use the source as the single source of truth.

If the source is incomplete or ambiguous, preserve that uncertainty rather
than filling gaps with assumptions.

Prefer user-visible behaviour over implementation details.

Treat implementation details (such as API names, database changes,
framework code, CSS classes, internal methods, developer notes, or
architecture) as supporting context rather than independent test
requirements unless they describe observable behaviour or explicit
acceptance criteria.

Do not invent:

- product behaviour
- acceptance criteria
- business rules
- validation rules
- user journeys
- selectors
- routes
- endpoints
- APIs
- request payloads
- database state
- fixtures
- test accounts
- permissions
- UI elements

unless they are explicitly supported by the source.

If a route, selector, API, fixture, account, permission, or technical
implementation detail is not present in the source, do not include it.
Later pipeline stages will provide implementation context.

Return ONLY valid JSON.
Do not include markdown, explanations, comments, or code fences.

Required JSON shape:

{
  "title": "short feature or flow name",
  "description": "brief summary of the requested behaviour",
  "acceptance_criteria": [
    "criteria explicitly present or directly restated from the source"
  ],
  "affected_pages": [
    "snake_case page, screen, module, or endpoint names when supported by the source"
  ],
  "user_types": [
    "snake_case user roles or user states when supported by the source"
  ],
  "test_cases": [
    {
      "id": "TC_001",
      "title": "action-oriented test case title",
      "preconditions": [
        "required setup or state"
      ],
      "steps": [
        "ordered user or system actions"
      ],
      "expected_result": "observable outcome to assert",
      "tags": [
        "snake_case labels"
      ]
    }
  ]
}

Extraction rules:

- Preserve the original business meaning.
- Restate acceptance criteria only when directly supported by the source.
- Split independent user journeys into separate test cases.
- If a CTA, navigation assertion, unlock prompt, or follow-on page action continues the same happy-path journey, keep it in the same test case.
- Do not create a separate test case whose precondition is simply that the user is already on a page or state reached by a previous step in the same journey.
- Split only when the outcome is independent, alternative, or requires a genuinely different setup.
- Generate test cases around complete user goals rather than individual UI widgets.
- Group related validations into one test case when they belong to the same user flow.
- Create separate test cases for distinct outcomes (such as success, validation failure, permission denial, or empty state) only when they are explicitly described or logically required to verify an explicit acceptance criterion.
- Do not generate speculative edge cases or unsupported scenarios.
- Every test case must have an observable expected_result.
- Keep steps minimal and implementation-agnostic.
- Use snake_case for affected_pages, user_types, and tags.
- Rich requirements should typically produce 3-15 focused test cases.
- Sparse requirements may legitimately produce fewer test cases.
- When information is missing, prefer fewer, higher-confidence test cases over speculative coverage.

Fidelity rules:

- Never add an outcome that is not explicitly stated in the source.
- Do not infer redirects, destinations, dashboards, success pages, or navigation
  after authentication unless the source explicitly states them.
- Do not add technical or environmental preconditions such as services being
  configured, APIs being available, authentication providers being configured,
  or test data existing unless explicitly stated in the source.
- Preserve "and" versus "or" semantics from the source.
- Do not strengthen an acceptance criterion. For example, if the source says
  "incorrect email or password", do not change this to requiring both an
  incorrect email and an incorrect password.
- Use natural human-readable text for title, description, acceptance_criteria,
  test case titles, preconditions, steps, and expected_result.
- Use snake_case ONLY for affected_pages, user_types, and tags.
A plausible assumption is still an invention.
If the source says "user is successfully authenticated", the expected result
must not become "user is authenticated and redirected to the dashboard".

Return valid JSON only.
""".strip()


class Stage1ParserAgent:
    def __init__(self, config: AgentConfig | None = None):
        self.config = config or AgentConfig.load()
        self.client = OpenAI(
            api_key=self.config.openai_api_key,
            base_url=self.config.openai_base_url or None,
        )

    def extract(
        self,
        content: str,
        source: str | Path,
        title: str | None = None,
        input_source: InputSource = InputSource.TEXT,
    ) -> TestSpec:
        validate_stage1_input(content)
        title_line = f"Known title: {title}\n\n" if title else ""
        user_prompt = (
            f"/no_think\n\n"
            f"{title_line}"
            f"Source: {source}\n\n"
            f"Raw ticket or requirement text:\n{content}"
        )
        response = self.client.chat.completions.create(
            model=self.config.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            **self.config.token_limit_kwargs(4000),
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        data = {
            "source": input_source,
            "source_id": str(source),
            "raw_content": content,
            **payload,
        }
        if title:
            data["title"] = title
        if not data.get("title"):
            source_text = str(source)
            if source_text.lower().startswith(("http://", "https://")):
                parsed = urlparse(source_text)
                data["title"] = parsed.netloc + parsed.path.rstrip("/")
            else:
                data["title"] = Path(source_text).stem
        return TestSpec.model_validate(data)
