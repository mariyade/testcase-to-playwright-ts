# Quality Engineering Strategy

## Purpose

This document describes the quality principles and testing standards used by this
project. It explains how quality is assessed, how AI-assisted testing supports the
workflow, and how defects are reported consistently.

## Quality Philosophy

Quality is more than checking whether a feature works. The goal is to reduce business
risk by validating functionality, usability, reliability, accessibility, and resilience
under realistic user behaviour.

Testing should prevent production defects, not simply confirm the expected happy path.

Automation is one part of quality engineering. It complements exploratory testing, code reviews, monitoring, and good engineering practices—it doesn't replace them.

## Testing Principles

### Risk-Based Testing

Prioritise testing by business impact:

1. Authentication
2. Authorisation
3. Payments
4. Data persistence
5. Core business workflows
6. Integrations
7. Search
8. Reporting
9. Cosmetic UI

### Behaviour Over Implementation

Tests should verify observable user behaviour. Avoid asserting implementation details
unless they are part of the contract under test.

Prefer:

```text
User sees the booking confirmation.
```

Avoid:

```text
Internal helper function was called.
```

### Happy path is only the starting point

If the happy path passes, the feature is probably usable.

It doesn't tell us how the application behaves when users make mistakes, data is missing, requests fail, or state changes unexpectedly.

For most features I expect to test:

- valid input/successfull submission
- invalid input
- boundary values
- empty values
- duplicate actions
- browser refresh
- interrupted requests
- navigation away and back
- expired sessions
- unexpected user actions

## Exploratory Testing

Exploratory testing complements automated checks. Areas to investigate include:

- Navigation and browser history
- Duplicate clicks and repeated submissions
- Keyboard navigation and focus handling
- Accessibility labels and roles
- Loading, empty, and error states
- Responsive layouts
- Form validation
- API failures surfaced through the UI

## Test Pyramid

### Unit Tests

Use unit tests for fast feedback around isolated business logic, parsers, utilities,
schemas, and deterministic transformations.

### Integration Tests

Use integration tests for API contracts, service boundaries, database behaviour,
retrieval pipelines, and dependency wiring.

### End-To-End Tests

Use E2E tests for critical user journeys only. Keep them focused, deterministic, and
valuable enough to justify browser cost.

## Automation Principles

Automation should be:

- Deterministic
- Maintainable
- Independent
- Repeatable
- Readable

Avoid:

- Hard waits
- Brittle selectors
- Duplicated setup logic
- Tests that depend on execution order
- Assertions on unstable public demo data

Prefer:

- Page objects
- Reusable fixtures
- Explicit assertions
- Stable locators
- Fresh test data
- Clear setup and teardown

## Playwright Standards

Preferred locator order:

1. `getByRole()`
2. `getByLabel()`
3. `getByPlaceholder()`
4. `getByTestId()`

Avoid XPath unless necessary. Do not depend on CSS hierarchy or layout-specific selectors.

Use explicit expectations such as:

```ts
await expect(locator).toBeVisible();
await expect(locator).toHaveText(/confirmed/i);
await expect(page).toHaveURL(/booking/);
await expect(button).toBeEnabled();
```

Avoid arbitrary sleeps such as:

```ts
await page.waitForTimeout(1000);
```

## AI-Assisted Testing

AI should assist engineers, not replace engineering judgement.

AI may help:

- Generate test ideas
- Identify edge cases
- Improve coverage
- Explain failures
- Create regression candidates
- Compare generated tests against acceptance criteria

AI should never:

- Fabricate observations
- Invent evidence
- Claim tests passed without execution
- Guess application behaviour
- Generate credentialed flows without credentials
- Hide uncertainty

## Evidence Collection

Every defect should include:

- Screenshot or trace where relevant
- URL and environment
- Preconditions
- Reproduction steps
- Expected result
- Actual result
- Console errors where relevant
- Network evidence where relevant
- Business risk

## Severity Classification

### Critical

- Data loss
- Security issue
- Payment failure
- Application unavailable

### High

- Major workflow broken
- Incorrect business behaviour
- Core functionality unusable

### Medium

- Partial functionality broken
- Validation issue
- UI issue that blocks or slows completion

### Low

- Visual defect
- Copy issue
- Spacing or minor consistency issue

## Definition Of Done

A feature is considered complete when:

- Acceptance criteria are satisfied
- Relevant automated tests pass
- Regression risk has been considered
- No Critical defects remain
- No High defects remain without explicit acceptance
- Evidence is recorded for material testing
- Documentation is updated where required

## Reporting Standards

Testing reports should include:

- Scope
- Environment
- Scenarios executed
- Passed checks
- Failed checks
- Blocked checks
- Defects found
- Business risks
- Recommendations
- Remaining unknowns

Clearly distinguish observed facts from assumptions and recommendations.

## Continuous Improvement

Testing standards should evolve based on:

- Production incidents
- Recurring defects
- Customer feedback
- Automation failures
- Flaky tests
- Post-release reviews

Quality engineering is an iterative process rather than a fixed checklist.

# Reporting

A useful testing report answers four questions:

**What was tested?**

Describe the scope.

**What happened?**

Summarise the executed scenarios.

**What problems were found?**

List defects with evidence.

**What should happen next?**

Highlight risks, recommendations, and any remaining unknowns.

I always try to separate:

- observed facts
- assumptions
- recommendations

Mixing these together often causes confusion.
