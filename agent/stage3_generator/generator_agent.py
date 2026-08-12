from __future__ import annotations

import re

from openai import OpenAI

from agent.config import AgentConfig
from agent.models import RepoContext, TestSpec
from agent.stage3_generator.generation_payload import (
    generated_files_from_payload,
    parse_generation_payload,
)
from agent.stage3_generator.generation_types import GenerationResult
from agent.stage3_generator.generation_validation import validate_generated_files
from agent.stage3_generator.prompting import SYSTEM_PROMPT, build_generation_prompt
from agent.stage3_generator.tools import ToolCall, execute_tool_call, tool_registry


# Orchestrates Stage 3: prompt the model, handle tools, validate, retry once, then save files.
class Stage3GeneratorAgent:
    # Create the OpenAI-compatible client used for Stage 3 generation.
    def __init__(self, config: AgentConfig | None = None):
        self.config = config or AgentConfig.load()
        self.client = OpenAI(
            api_key=self.config.openai_api_key,
            base_url=self.config.openai_base_url or None,
        )

    # Generate Playwright specs from a TestSpec and Stage 2 RepoContext.
    # Missing capabilities/grounding are handled before the model sees executable cases.
    def generate(
        self,
        spec: TestSpec,
        context: RepoContext,
        feedback: str = "",
        dry_run: bool = False,
    ) -> GenerationResult:
        slug = re.sub(r"[^a-z0-9]+", "_", spec.title.lower()).strip("_") or "generated_test"
        output_scope = context.implementation.output_scope
        tool_calls: list[str] = []
        current_feedback = feedback
        tools = tool_registry(self.config.project_root / "agent" / "vector_store")

        for repair_attempt in range(2):
            raw = self._generate_raw_response(spec, context, current_feedback, tools, tool_calls)
            payload = parse_generation_payload(raw)
            model_files = generated_files_from_payload(payload, context, slug, output_scope)
            # Output guardrail: reject invalid generated code before saving.
            validation_errors = validate_generated_files(model_files, context, spec)
            code = "\n\n".join(file.code for file in model_files).strip()

            if validation_errors:
                if any("does not include a file path" in error for error in validation_errors):
                    return GenerationResult(
                        False,
                        code=code,
                        files=[],
                        error="Invalid generated Playwright code:\n- "
                        + "\n- ".join(validation_errors),
                        tool_calls=tool_calls,
                    )
                if repair_attempt == 0:
                    current_feedback = _refine_feedback(feedback, validation_errors)
                    continue
                return GenerationResult(
                    False,
                    code=code,
                    files=[],
                    error="Invalid generated Playwright code:\n- " + "\n- ".join(validation_errors),
                    tool_calls=tool_calls,
                )

            if not code:
                return GenerationResult(
                    False,
                    error="Model returned no code",
                    tool_calls=tool_calls,
                )

            return _write_generation_result(
                generated_files=model_files,
                context=context,
                dry_run=dry_run,
                code=code,
                tool_calls=tool_calls,
            )

        return GenerationResult(
            False,
            error="Stage 3 generation exited unexpectedly.",
            tool_calls=tool_calls,
        )

    # Run one model attempt, including any tool-call rounds.
    def _generate_raw_response(self, spec, context, feedback, tools, tool_calls) -> str:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_generation_prompt(spec, context, feedback)},
        ]
        for _tool_round in range(self.config.max_tool_rounds):
            response = self.client.chat.completions.create(
                model=self.config.openai_model,
                messages=messages,
                tools=tools.schema,
                tool_choice="auto",
                response_format={"type": "json_object"},
                temperature=0,
                **self.config.token_limit_kwargs(6000),
            )
            choice = response.choices[0]

            if choice.finish_reason != "tool_calls":
                return choice.message.content or ""

            messages.append(choice.message)
            for call in choice.message.tool_calls or []:
                tool_call = ToolCall.from_openai(call)
                tool_calls.append(f"{tool_call.name}({tool_call.arguments})")
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": execute_tool_call(context, tool_call, tools),
                    }
                )
        return ""


# Build the one refinement prompt from deterministic validation errors.
def _refine_feedback(original_feedback: str, validation_errors: list[str]) -> str:
    validation_feedback = "\n".join(
        [
            "Reflect on the generated Playwright code before regenerating.",
            "The previous output failed deterministic Stage 3 validation.",
            "Fix only the issues listed below.",
            "Keep valid files and test intent unchanged.",
            "Return the full corrected JSON response with files[].",
            "",
            "Validation errors:",
            *[f"- {error}" for error in validation_errors],
        ]
    )
    if original_feedback:
        return f"{original_feedback}\n\n{validation_feedback}"
    return validation_feedback


# Write generated specs and sidecar missing-data reports unless this is a dry run.
def _write_generation_result(
    *,
    generated_files,
    context: RepoContext,
    dry_run: bool,
    code: str,
    tool_calls: list[str],
) -> GenerationResult:
    primary_file = generated_files[0]
    filepath = primary_file.path
    if not dry_run:
        for generated_file in generated_files:
            generated_file.path.parent.mkdir(parents=True, exist_ok=True)
            generated_file.path.write_text(generated_file.code, encoding="utf-8")

    return GenerationResult(
        True,
        code=code,
        filepath=None if dry_run else filepath,
        files=[] if dry_run else generated_files,
        tool_calls=tool_calls,
    )
