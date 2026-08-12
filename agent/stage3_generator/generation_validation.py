from __future__ import annotations

import re

from agent.models import RepoContext, TestSpec
from agent.stage3_generator.generation_types import GeneratedFile


# Run lightweight pipeline-specific validation before files are saved.
# TypeScript/Playwright checks still own syntax and framework correctness.
def validate_generated_files(
    files: list[GeneratedFile], context: RepoContext, spec: TestSpec
) -> list[str]:
    page_contracts = _page_object_contracts(context)
    file_by_test_case = {
        test_case.id: [file for file in files if test_case.id in file.path.as_posix()]
        for test_case in spec.test_cases
    }
    errors: list[str] = []

    for file in files:
        if re.search(r"\bpage\.pause\s*\(", file.code):
            errors.append(f"{file.path.name} contains page.pause(), which must not be generated.")
        errors.extend(_validate_proposed_method_markers(file, page_contracts))

    errors.extend(_validate_test_case_coverage(spec, file_by_test_case))
    return errors


# Ensure each TestSpec case has exactly one generated file with a Playwright test.
def _validate_test_case_coverage(
    spec: TestSpec, file_by_test_case: dict[str, list[GeneratedFile]]
) -> list[str]:
    errors: list[str] = []
    for test_case in spec.test_cases:
        files = file_by_test_case[test_case.id]
        if not files:
            errors.append(
                f"Generated output does not include a file path for {test_case.id}; "
                "generation is incomplete or required grounded data is unavailable."
            )
            continue
        if len(files) > 1:
            errors.append(f"Generated output includes multiple files for {test_case.id}.")
    return errors


# Unknown page-object methods are allowed only when clearly marked for review.
def _validate_proposed_method_markers(
    file: GeneratedFile, page_contracts: dict[str, dict]
) -> list[str]:
    errors: list[str] = []
    for fixture_name, contract in page_contracts.items():
        pattern = re.compile(rf"\b{re.escape(fixture_name)}\.([A-Za-z_][A-Za-z0-9_]*)\s*\(")
        for match in pattern.finditer(file.code):
            method_name = match.group(1)
            if method_name in contract["methods"]:
                continue
            before_call = file.code[: match.start()].rstrip().splitlines()
            has_proposed_comment = bool(
                before_call and before_call[-1].strip().startswith("// PROPOSED:")
            )
            if not has_proposed_comment:
                errors.append(
                    f"{file.path.name} calls proposed method {fixture_name}.{method_name}() "
                    "without this exact comment immediately above the call: "
                    "// PROPOSED: Missing RepositoryContracts method - human review required."
                )
    return errors


# Build a lookup from fixture name to its page-object contract.
def _page_object_contracts(context: RepoContext) -> dict[str, dict]:
    contracts: dict[str, dict] = {}
    for page in context.page_objects:
        fixture = page.fixture or f"{page.name[:1].lower()}{page.name[1:]}"
        contracts[fixture] = {
            "page_object": page.name,
            "filepath": page.filepath,
            "methods": {method.name: method for method in page.methods},
        }
    return contracts
