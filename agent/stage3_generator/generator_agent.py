from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from openai import OpenAI

from agent.config import AgentConfig
from agent.models import RepoContext, TestSpec
from agent.stage3_generator.prompt_builder import SYSTEM_PROMPT, build_generation_prompt
from agent.stage3_generator.tools import ToolDispatcher, tool_schemas


@dataclass
class GenerationResult:
    success: bool
    code: str = ""
    filepath: Path | None = None
    tool_calls: list[str] = field(default_factory=list)
    error: str = ""
    tokens_used: int = 0


class GeneratorAgent:
    def __init__(self, config: AgentConfig | None = None):
        self.config = config or AgentConfig.load()
        self.client = OpenAI(api_key=self.config.openai_api_key)

    def generate(
        self,
        spec: TestSpec,
        context: RepoContext,
        feedback: str = "",
        dry_run: bool = False,
    ) -> GenerationResult:
        dispatcher = ToolDispatcher(context)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_generation_prompt(spec, context, feedback)},
        ]
        tool_calls: list[str] = []
        tokens = 0
        raw = ""

        for _ in range(self.config.max_tool_rounds):
            response = self.client.chat.completions.create(
                model=self.config.openai_model,
                messages=messages,
                tools=tool_schemas(),
                tool_choice="auto",
                max_tokens=6000,
            )
            choice = response.choices[0]
            if response.usage:
                tokens += response.usage.prompt_tokens + response.usage.completion_tokens

            if choice.finish_reason == "tool_calls":
                messages.append(choice.message)
                for call in choice.message.tool_calls or []:
                    name = call.function.name
                    args = json.loads(call.function.arguments or "{}")
                    tool_calls.append(f"{name}({args})")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": dispatcher.dispatch(name, args),
                    })
                continue

            raw = choice.message.content or ""
            break

        code = _strip_markdown(raw)
        if not code:
            return GenerationResult(False, error="Model returned no code", tool_calls=tool_calls, tokens_used=tokens)

        filepath = _output_path(context.playwright_root, spec)
        if not dry_run:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(code, encoding="utf-8")

        return GenerationResult(
            True,
            code=code,
            filepath=None if dry_run else filepath,
            tool_calls=tool_calls,
            tokens_used=tokens,
        )


def _strip_markdown(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
    return stripped.strip()


def _output_path(playwright_root: Path, spec: TestSpec) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "_", spec.title.lower()).strip("_") or "generated_test"
    return playwright_root / "tests" / "generated" / f"{slug}.spec.ts"
