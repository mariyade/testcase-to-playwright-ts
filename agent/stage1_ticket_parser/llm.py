from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from openai import OpenAI

from agent.config import AgentConfig
from agent.models import InputSource, TestSpec

SYSTEM_PROMPT = """
You are Stage 1 of a QA agent. Convert an incoming requirement,
ticket, issue, or free-text note into one normalized TestSpec JSON object for
downstream Playwright test generation.

Read the source as evidence. Preserve explicit requirements, acceptance
criteria, user roles, affected areas, and testable outcomes. When the source
contains enough detail, split the work into focused test cases that cover the
main success path, supported error paths, and meaningful boundaries. When the
source is sparse, keep the output conservative instead of filling gaps with
assumptions.

Return only valid JSON. Do not include markdown, commentary, or code fences.

Required JSON shape:
{
  "title": "short feature or flow name",
  "description": "brief summary of the requested behavior",
  "acceptance_criteria": ["criteria explicitly present or directly restated from the source"],
  "affected_pages": ["snake_case page, screen, module, or endpoint names when supported by the source"],
  "user_types": ["snake_case user roles or states when supported by the source"],
  "test_cases": [
    {
      "id": "TC_001",
      "title": "action-oriented test case title",
      "priority": "Critical|High|Medium|Low",
      "type": "Smoke|Regression|Sanity",
      "preconditions": ["required setup or state"],
      "steps": ["ordered user or system actions"],
      "expected_result": "observable outcome to assert",
      "tags": ["short labels from the source or inferred from explicit context"]
    }
  ]
}

Extraction rules:
- Use the source language as the authority. Do not invent product behavior, selectors, routes, accounts, data, APIs, permissions, or UI states.
- Normalize names to snake_case in affected_pages, user_types, and tags.
- Use Critical only for flows whose failure blocks a primary business or user journey.
- Use High for important customer-visible behavior that does not fully block the main journey.
- Use Medium or Low for secondary, informational, or low-risk behavior.
- Use Smoke for minimal happy-path coverage, Regression for deeper behavior coverage, and Sanity for quick post-change checks.
- Include negative, permission, validation, or empty-state cases only when the source implies or states those behaviors.
- Prefer 3 to 15 test cases for rich tickets. For sparse input, fewer test cases are acceptable.
- Every test case must have an observable expected_result. If steps are missing from the source, keep steps minimal and do not invent unavailable implementation details.
""".strip()


class Stage1ParserAgent:
    def __init__(self, config: AgentConfig | None = None):
        self.config = config or AgentConfig.load()
        self.client = OpenAI(api_key=self.config.openai_api_key)

    def extract(
        self,
        content: str,
        source: str | Path,
        title: str | None = None,
        input_source: InputSource = InputSource.TEXT,
    ) -> TestSpec:
        title_line = f"Known title: {title}\n\n" if title else ""
        user_prompt = f"{title_line}Source: {source}\n\nRaw ticket or requirement text:\n{content}"

        response = self.client.chat.completions.create(
            model=self.config.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=4000,
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
