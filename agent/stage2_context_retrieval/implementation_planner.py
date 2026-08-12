from __future__ import annotations

import re

from agent.models import (
    ImplementationPlan,
    PageObjectInfo,
    PageObjectMethodInfo,
    RepoContext,
    TestCaseImplementation,
)


# Build the plan that tells Stage 3 which page object/methods each test may use.
# Stage 1 remains the "what to test"; this adds the repository "how to automate it".
def enrich_implementation_plan(context: RepoContext, spec) -> ImplementationPlan:
    return ImplementationPlan(
        output_scope=_output_scope(spec),
        test_cases=[
            _implementation_for_test_case(context, spec, test_case) for test_case in spec.test_cases
        ],
    )


# Pick the best page object for one test case and summarize what can be automated.
# If no page object matches, the whole test text is reported as missing capability.
def _implementation_for_test_case(context: RepoContext, spec, test_case) -> TestCaseImplementation:
    text = _test_case_text(spec, test_case)
    outcome_text = _test_case_outcome_text(spec, test_case)
    expected_text = (test_case.expected_result or "").lower()
    scored_pages = [
        (
            _page_implementation_score(page_object, text, outcome_text, expected_text),
            _satisfied_clause_count(page_object, spec, test_case),
            page_object,
        )
        for page_object in context.page_objects
    ]
    scored_pages = [
        (score, matched_clauses, page_object)
        for score, matched_clauses, page_object in scored_pages
        if score > 0
    ]
    primary_page = (
        max(scored_pages, key=lambda item: (item[0], item[1]))[2] if scored_pages else None
    )

    return TestCaseImplementation(
        test_case_id=test_case.id,
        primary_page_object=primary_page.name if primary_page else "",
        required_methods=_required_methods_for_test_case(primary_page, spec, test_case)
        if primary_page
        else [],
        missing_capabilities=_missing_capabilities_for_test_case(primary_page, spec, test_case)
        if primary_page
        else [_test_case_text(spec, test_case)],
    )


# Return the unique page-object methods Stage 3 is allowed to call for this case.
# dict.fromkeys preserves the planner order while removing duplicates.
def _required_methods_for_test_case(page_object: PageObjectInfo, spec, test_case) -> list[str]:
    planned = _method_plan_for_test_case(page_object, spec, test_case)
    return list(dict.fromkeys(method for method, _clause in planned))


# Identify required steps/outcomes that no selected page-object method covers.
# Preconditions and direct Playwright navigation assertions are intentionally ignored.
def _missing_capabilities_for_test_case(page_object: PageObjectInfo, spec, test_case) -> list[str]:
    planned = _method_plan_for_test_case(page_object, spec, test_case)
    planned_clauses = {clause for _method, clause in planned}
    missing: list[str] = []
    for clause in _implementation_clauses(spec, test_case):
        if clause["optional"]:
            continue
        if clause["kind"] == "precondition":
            continue
        if _is_framework_level_assertion(clause):
            continue
        if clause["text"] not in planned_clauses:
            missing.append(clause["text"])
    return missing


# Count how many non-precondition clauses a page object can satisfy.
# This breaks ties between pages with similar text relevance.
def _satisfied_clause_count(page_object: PageObjectInfo, spec, test_case) -> int:
    return sum(
        1
        for clause in _implementation_clauses(spec, test_case)
        if clause["kind"] != "precondition" and _best_method_for_clause(page_object, clause)
    )


# Detect outcomes that Playwright can assert directly with page URL checks.
# These should not become missing page-object helper requests.
def _is_framework_level_assertion(clause: dict[str, str | bool]) -> bool:
    if clause["kind"] not in {"step", "expected"}:
        return False
    text = str(clause["text"])
    has_navigation_word = re.search(
        r"\b(reaches|navigate|navigates|navigated|redirect|redirects|redirected|taken|lands|arrives)\b",
        text,
    )
    has_page_or_route = "page" in text or re.search(r"/[a-z0-9_-]+", text)
    return bool(has_navigation_word and has_page_or_route)


# Match each precondition/step/expected-result clause to the best page-object method.
# The result keeps both method name and clause text so missing capability checks can compare.
def _method_plan_for_test_case(
    page_object: PageObjectInfo, spec, test_case
) -> list[tuple[str, str]]:
    planned: list[tuple[str, str]] = []
    for clause in _implementation_clauses(spec, test_case):
        method = _best_method_for_clause(page_object, clause)
        if method:
            planned.append((method.name, clause["text"]))
    return planned


# Convert a TestCase into small lowercase clauses for method matching.
# Each clause keeps its role so actions and assertions can be treated differently.
def _implementation_clauses(spec, test_case) -> list[dict[str, str | bool]]:
    del spec
    clauses: list[dict[str, str | bool]] = []
    for precondition in test_case.preconditions:
        clauses.append(
            {
                "kind": "precondition",
                "text": precondition.lower(),
                "optional": False,
            }
        )
    for step in test_case.steps:
        clauses.append(
            {
                "kind": "step",
                "text": step.lower(),
                "optional": False,
            }
        )
    if test_case.expected_result:
        clauses.append(
            {
                "kind": "expected",
                "text": test_case.expected_result.lower(),
                "optional": False,
            }
        )
    return clauses


# Select the best method for one clause using the planner's lexical score.
# A zero score means no repository method should be treated as a match.
def _best_method_for_clause(page_object: PageObjectInfo, clause: dict[str, str | bool]):
    scored = [
        (_method_clause_score(page_object, method, clause), method)
        for method in page_object.methods
    ]
    scored = [(score, method) for score, method in scored if score > 0]
    if not scored:
        return None
    return max(scored, key=lambda item: item[0])[1]


# Score whether a method's intent, name, and parameters fit a requirement clause.
# Expected-result clauses are restricted to assertion methods, and actions are not.
def _method_clause_score(
    page_object: PageObjectInfo,
    method: PageObjectMethodInfo,
    clause: dict[str, str | bool],
) -> int:
    text = str(clause["text"])
    kind = str(clause["kind"])
    if _requires_named_external_provider(text, method):
        return 0
    if _requires_password_recovery(text, method):
        return 0
    if kind == "precondition":
        return 8 if _method_opens_page(method, page_object, text) else 0
    intent_tokens = _intent_tokens(method.intent or method.name)
    method_tokens = _intent_tokens(method.name)
    score = 0

    if method.name.startswith("expect") and kind != "expected":
        return score
    if kind == "expected" and not method.name.startswith("expect"):
        return score

    for token in intent_tokens:
        if len(token) > 2 and token in text:
            score += 3
    for token in method_tokens:
        if len(token) > 2 and token in text:
            score += 1
    for token in _method_parameter_tokens(method):
        if len(token) > 2 and token in text:
            score += 2

    if method.name.startswith("expect") and score:
        score += 2
    return score


# Avoid mapping external-provider flows, such as Google login, to unrelated helpers.
# The method must mention the same provider before it can be considered a match.
def _requires_named_external_provider(text: str, method: PageObjectMethodInfo) -> bool:
    providers = {"google", "oauth", "sso", "single sign on", "third party", "third-party"}
    if not any(provider in text for provider in providers):
        return False
    method_text = " ".join([method.name, method.intent, method.signature]).lower()
    return not any(provider in method_text for provider in providers)


# Avoid using a generic login/registration method for password recovery flows.
# A matching method must explicitly mention forgot/reset/recover wording.
def _requires_password_recovery(text: str, method: PageObjectMethodInfo) -> bool:
    if not re.search(
        r"\b(forgot|reset|recover)\b.*\bpassword\b|\bpassword\b.*\b(reset|recover)\b", text
    ):
        return False
    method_text = " ".join([method.name, method.intent, method.signature]).lower()
    return not re.search(r"\b(forgot|reset|recover)\b", method_text)


# Decide whether a method can establish a "user is on page X" precondition.
# It accepts explicit navigation targets or page-opening intent words.
def _method_opens_page(
    method: PageObjectMethodInfo, page_object: PageObjectInfo, text: str
) -> bool:
    page_terms = {
        page_object.page.replace("_", " "),
        page_object.page.removesuffix("_page").replace("_", " "),
        re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", page_object.name).lower(),
    }
    mentions_page = any(term and term in text for term in page_terms)
    if not mentions_page:
        return False
    if method.navigates_to == page_object.name:
        return True
    return bool({"open", "goto", "page"} & set(_intent_tokens(method.intent or method.name)))


# Convert names like expectMetricValue or update_search into comparable tokens.
# Synonyms are appended so common QA wording can still match terse method names.
def _intent_tokens(value: str) -> list[str]:
    readable = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value).lower()
    tokens = [token for token in re.split(r"[^a-z0-9]+", readable) if token]
    return tokens + _synonym_tokens(tokens)


# Add method argument names/types/object fields to the matching vocabulary.
# This helps a clause about "email" or "budget" match methods with structured data.
def _method_parameter_tokens(method: PageObjectMethodInfo) -> list[str]:
    tokens: list[str] = []
    for parameter in method.parameters:
        tokens.extend(_intent_tokens(parameter.name))
        tokens.extend(_intent_tokens(parameter.type))
        for property_name in parameter.properties:
            tokens.extend(_intent_tokens(property_name))
    return tokens


# Expand a few common domain-neutral terms used differently in stories and code.
# This is intentionally small so the planner does not become a hand-built NLP engine.
def _synonym_tokens(tokens: list[str]) -> list[str]:
    synonyms = {
        "login": ["sign", "in", "authenticate", "authenticated"],
        "authenticated": ["login", "signed", "in"],
        "authentication": ["login", "sign", "in"],
        "error": ["invalid"],
        "validation": ["required", "missing"],
    }
    expanded: list[str] = []
    for token in tokens:
        expanded.extend(synonyms.get(token, []))
    return expanded


# Combine story, acceptance criteria, affected pages, and case details.
# This broad text is used for page relevance and general method matching.
def _test_case_text(spec, test_case) -> str:
    parts = [
        spec.title,
        spec.description,
        " ".join(spec.acceptance_criteria),
        " ".join(spec.affected_pages),
        test_case.title,
        " ".join(test_case.preconditions),
        " ".join(test_case.steps),
        test_case.expected_result,
        " ".join(test_case.tags),
    ]
    return "\n".join(part for part in parts if part).lower()


# Build a smaller text view weighted toward expected business outcomes.
# Page scoring uses this to avoid overvaluing incidental setup wording.
def _test_case_outcome_text(spec, test_case) -> str:
    parts = [
        spec.title,
        " ".join(spec.acceptance_criteria),
        test_case.title,
        test_case.expected_result,
        " ".join(test_case.tags),
    ]
    return "\n".join(part for part in parts if part).lower()


# Score how strongly a page object appears to own this test case.
# Mentions in expected outcomes count more than broad mentions in the whole story.
def _page_implementation_score(
    page_object: PageObjectInfo,
    text: str,
    outcome_text: str,
    expected_text: str,
) -> int:
    score = 0
    page_token = page_object.page.removesuffix("_page").replace("_", " ")
    object_token = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", page_object.name).lower()
    fixture_token = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", page_object.fixture).lower()

    for token in {page_token, object_token, fixture_token}:
        if not token:
            continue
        if token in expected_text:
            score += 12
        elif token in outcome_text:
            score += 8
        elif token in text:
            score += 4

    for method in page_object.methods:
        if method.intent and _text_mentions(text, method.intent):
            score += 2
        if method.navigates_to and method.navigates_to.lower() in text:
            score += 1
    return score


# Check whether text contains either human-readable or compact code-style wording.
# For example, "login page" and "loginpage" can both match the same value.
def _text_mentions(text: str, value: str) -> bool:
    readable = value.replace("_", " ").lower()
    compact = value.replace("_", "").lower()
    return readable in text or compact in text.replace(" ", "")


# Use a Jira-style key as the generated folder name when possible.
# Free-text inputs fall back to a stable "free-text" scope.
def _output_scope(spec) -> str:
    source_text = f"{spec.source_id} {spec.title}"
    match = re.search(r"\b([A-Z][A-Z0-9]+-\d+)\b", source_text.upper())
    if match:
        return match.group(1)
    return "free-text"
