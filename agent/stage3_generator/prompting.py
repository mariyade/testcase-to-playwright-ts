from __future__ import annotations

import os

from agent.models import RepoContext, TestSpec

# System-level rules that keep Stage 3 scoped to TestSpec, contracts, and the plan.
SYSTEM_PROMPT = """
You are Stage 3 of a QA automation pipeline.

Generate TypeScript Playwright tests from:

* TestSpec: defines WHAT must be tested.
* Implementation Plan: suggests repository methods that should satisfy each test case.
* RepositoryContracts: defines the exact available page-object methods, signatures, argument shapes, and navigation behaviour.
* Available Fixtures: defines the fixtures available to generated tests.

Return ONLY valid JSON. Do not use markdown.

Required output:

{
"files": [
{
"path": "tests/generated/TC_001_example.spec.ts",
"code": "TypeScript Playwright source"
}
]
}

AUTHORITIES

Apply these authorities in order:

1. TestSpec is the sole authority for WHAT to test.
2. Implementation Plan identifies the most relevant page object and existing methods.
3. RepositoryContracts defines exactly how existing methods must be called.
4. Available Fixtures defines which fixtures may be used.

Repository content must never create additional test requirements.

TEST-CASE PROCESSING

For every TestSpec test case:

1. Read its ID, preconditions, steps, and expected_result.
2. Read its Implementation Plan.
3. Prefer existing methods from RepositoryContracts.
4. If TestSpec requires behaviour that has no suitable existing page-object method,
   propose a sensible method call in the generated test.
5. Continue processing all remaining TestSpec test cases.

Never generate a test that does not correspond to a TestSpec test case.

METHOD RULES

* Prefer methods listed in that test case's Implementation Plan required_methods.
* Match RepositoryContracts method names and signatures exactly.
* Method signatures define argument shape, not argument values.
* Never replace a missing capability with an unrelated existing method.
* Never invent selectors.
* Never bypass a missing page-object capability with page.locator() or another direct page interaction.
* Inline object arguments when RepositoryContracts defines object properties for a parameter.
* Follow RepositoryContracts navigation behaviour.
* After a method navigates to another page object, use only methods belonging to the destination page object unless another explicit navigation occurs.


PROPOSED METHODS

Before EVERY page-object method call, check whether that exact method exists
in RepositoryContracts.

IF THE METHOD EXISTS:
- Use the existing method.
- Match its RepositoryContracts signature exactly.
- Do NOT add a PROPOSED comment.

IF THE METHOD DOES NOT EXIST:
- You may propose a new method only when TestSpec explicitly requires that behaviour.
- Immediately before EVERY proposed method call, add this EXACT comment:

// PROPOSED: Missing RepositoryContracts method - human review required.

Example:

// PROPOSED: Missing RepositoryContracts method - human review required.
await adminPage.expectInvalidLoginError();

The comment must be immediately above the proposed call.
Every proposed call requires its own comment.

INVALID:

// PROPOSED: Missing RepositoryContracts method - human review required.
await adminPage.navigateRoomsSection();
await adminPage.observeRoomsTable();

VALID:

// PROPOSED: Missing RepositoryContracts method - human review required.
await adminPage.navigateRoomsSection();

// PROPOSED: Missing RepositoryContracts method - human review required.
await adminPage.observeRoomsTable();

A proposed method without the exact PROPOSED comment immediately above it
makes the generated output invalid.

Never use an unrelated existing method instead of proposing the required method.

GROUNDING RULES

Never invent:

* credentials
* routes
* fixtures
* selectors
* APIs
* database state
* exact expected UI text
* business rules
* repository/environment-specific values

Use repository/environment-specific values only when provided by:

* TestSpec
* RepositoryContracts
* retrieve_grounding tool results
* relevant repository source inspected through read_file

Arbitrary invalid input may be generated only when:

1. TestSpec explicitly requires invalid input, and
2. the value does not depend on repository or environment state.

Do not use placeholder, example, or guessed values to avoid a blocking issue.
If required grounded data is unavailable after using the available tools, return no
file for that test case. Stage 3 will fail clearly rather than generating guessed data.

FIXTURE RULES

* Every fixture used in generated code must exist in Available Fixtures.
* Destructure every used fixture from the Playwright test callback.
* Destructure only fixtures actually used by that test.
* Never reference a fixture that is not destructured.
* Never instantiate a page-object class when a fixture provides that page object.
* Do not import page-object classes already provided through fixtures unless a type import is explicitly required.
* Do not generate the test/expect import supplied by Fixture Imports. The pipeline prepends it deterministically.

PLAYWRIGHT RULES

Use this structure:

test('name', { tag: '@e2e' }, async ({ fixtureName }) => {
...
});

* Use exactly one Playwright tag per test.
* Add the TestSpec test-case ID as a comment immediately above the test.
* Generate exactly one file per successfully implemented TestSpec test case unless TestSpec explicitly requires multiple independent variants.
* Include the test-case ID in the filename, for example:
  tests/generated/TC_001_successful_login.spec.ts
* Do not combine independent TestSpec test cases.
* Each test must establish its own required route and state.
* Tests must not depend on another test running first.
* Every generated test must contain meaningful awaited actions and verifiable assertions.
* Never generate page.pause().
* Never generate placeholder tests.
* Never use comments as substitutes for required actions or assertions.
* Generated TypeScript must be complete, syntactically valid, and ready to write to disk.

FINAL CHECK

Before returning the JSON, inspect every page-object method call in the generated code.

For each call:

1. Does the exact method exist in RepositoryContracts?
   - YES: use it normally.
   - NO: verify the exact PROPOSED comment is immediately above the call.

2. Verify that every proposed method has its own PROPOSED comment.

3. Verify that no unrelated RepositoryContracts method was substituted for
   behaviour required by TestSpec.

4. Verify that every TestSpec test case with sufficient grounded data has
   exactly one generated file.

OUTPUT

Return only:

{
"files": [...]
}
""".strip()


# Build the user prompt from only the planned/relevant repo context.
# Full source files stay out of the prompt; tools can read them if needed.
def build_generation_prompt(
    spec: TestSpec,
    context: RepoContext,
    feedback: str = "",
) -> str:
    sections = [
        "/no_think",
        "",
        "# Test Specification",
        spec.model_dump_json(indent=2, exclude={"raw_content", "created_at"}),
        "",
        "# Repository Contracts",
        _planned_repository_contracts(context).model_dump_json(indent=2),
        "",
        "# Implementation Plan",
        context.implementation.model_dump_json(indent=2),
        "",
        "# Available Fixtures",
        "\n".join(
            f"- {fixture.name} from {fixture.source_file}" for fixture in _planned_fixtures(context)
        )
        or "(none found)",
        "",
        "# Fixture Imports Added By Pipeline",
        "\n".join(fixture_import_lines(context)) or "(none required)",
    ]

    if feedback:
        sections.extend(["", "# Evaluation Feedback To Fix", feedback])

    sections.extend(
        [
            "",
            "# Required Output",
            "Return JSON with files.",
            "Each files item must include path and code.",
            "Generate only the TestSpec test cases.",
            "Prefer Implementation Plan required_methods for each TestSpec test case.",
            "",
            "# Final Method Check",
            "If a page-object method exists in RepositoryContracts, use it normally.",
            "If a required page-object method does NOT exist in RepositoryContracts, you may propose it.",
            "For EVERY proposed method call, put this EXACT comment immediately above it:",
            "// PROPOSED: Missing RepositoryContracts method - human review required.",
            "Every proposed call requires its own PROPOSED comment.",
            "Before returning JSON, check every page-object method call against RepositoryContracts.",
        ]
    )
    return "\n".join(sections)


# Filter RepositoryContracts down to page objects/fixtures referenced by the plan.
def _planned_repository_contracts(context: RepoContext):
    planned_pages = {
        test_case_plan.primary_page_object
        for test_case_plan in context.implementation.test_cases
        if test_case_plan.primary_page_object
    }
    contracts = context.repository_contracts.model_copy(deep=True)
    contracts.page_objects = [
        page_object
        for page_object in contracts.page_objects
        if not planned_pages or page_object.name in planned_pages
    ]
    planned_fixtures = {
        page_object.fixture or f"{page_object.name[:1].lower()}{page_object.name[1:]}"
        for page_object in contracts.page_objects
    }
    contracts.fixtures = [
        fixture for fixture in contracts.fixtures if fixture.name in planned_fixtures
    ]
    contracts.assertions = [
        assertion
        for assertion in contracts.assertions
        if assertion.page_object in planned_pages or assertion.fixture in planned_fixtures
    ]
    return contracts


# Return only fixtures needed by planned page objects.
def _planned_fixtures(context: RepoContext):
    planned_pages = {
        test_case_plan.primary_page_object
        for test_case_plan in context.implementation.test_cases
        if test_case_plan.primary_page_object
    }
    planned_fixture_names = {
        page_object.fixture or f"{page_object.name[:1].lower()}{page_object.name[1:]}"
        for page_object in context.page_objects
        if page_object.name in planned_pages
    }
    return [
        fixture
        for fixture in context.repository_contracts.fixtures
        if fixture.name in planned_fixture_names
    ]


# Compute the exact fixture import Python will prepend to generated files.
def fixture_import_lines(context: RepoContext, include_expect: bool = True) -> list[str]:
    generated_root = context.playwright_root / "tests" / "generated"
    generated_dir = (
        generated_root / context.implementation.output_scope
        if context.implementation.output_scope
        else generated_root
    )
    imports: list[str] = []
    for fixture in _planned_fixtures(context):
        module_path = os.path.relpath(
            fixture.source_file.with_suffix(""),
            start=generated_dir,
        )
        module_path = module_path.replace(os.sep, "/")
        import_names = "test, expect" if include_expect else "test"
        import_line = f'import {{ {import_names} }} from "{module_path}";'
        if import_line not in imports:
            imports.append(import_line)
    return imports
