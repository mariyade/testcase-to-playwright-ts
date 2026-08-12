from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class GuardResult:
    passed: bool
    error: str = ""


class InputGuardrailError(ValueError):
    """Raised when Stage 1 input contains data that should not be sent to an LLM."""


_PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|your|the)\s+(instructions?|prompts?|rules?|guidelines?)",
    r"forget\s+(your|all|previous)\s+(instructions?|prompts?|rules?|context)",
    r"disregard\s+(your|all|previous)\s+(instructions?|rules?|guidelines?)",
    r"you\s+are\s+now\s+a\s+",
    r"act\s+as\s+(if\s+you\s+(are|were)|a\s+)",
    r"pretend\s+(to\s+be|you\s+are)",
    r"your\s+new\s+(instructions?|role|task)\s+(is|are)",
    r"override\s+(your|the)\s+(guidelines?|instructions?|rules?)",
    r"\bsystem\s*:\s*you\s+are\b",
    r"\bassistant\s*:\s*",
    r"</?(system|user|assistant|prompt)>",
    r"new\s+system\s+prompt",
    r"jailbreak",
    r"do\s+anything\s+now",
    r"DAN\s+mode",
]

_SENSITIVE_PATTERNS = [
    ("private key block", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("OpenAI API key", r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    ("GitHub token", r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}\b"),
    ("Slack token", r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    ("AWS access key", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ("Google API key", r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    ("JWT token", r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    ("private key value", r"\b(?:0x)?[0-9a-fA-F]{64}\b"),
    ("credential in URL", r"https?://[^/\s:@]+:[^/\s:@]+@"),
    (
        "secret assignment",
        r"\b(?:api[_-]?key|access[_-]?token|secret|client[_-]?secret|jira[_-]?api[_-]?token)"
        r"\s*[:=]\s*['\"]?[^\s,'\"]{12,}",
    ),
    ("US SSN", r"\b\d{3}-\d{2}-\d{4}\b"),
]

_COMPILED_PROMPT_INJECTION = [
    re.compile(pattern, re.IGNORECASE) for pattern in _PROMPT_INJECTION_PATTERNS
]
_COMPILED_SENSITIVE = [
    (label, re.compile(pattern, re.IGNORECASE)) for label, pattern in _SENSITIVE_PATTERNS
]

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_SAFE_EMAIL_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "test.com",
    "localhost",
}

_PRESIDIO_ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "US_SSN",
    "IBAN_CODE",
    "IP_ADDRESS",
    "LOCATION",
]


def validate_stage1_input(text: str) -> None:
    result = check_stage1_input(text)
    if not result.passed:
        raise InputGuardrailError(result.error)


def check_stage1_input(text: str) -> GuardResult:
    for pattern in _COMPILED_PROMPT_INJECTION:
        if pattern.search(text):
            return GuardResult(False, "Prompt injection detected in input.")

    for label, pattern in _COMPILED_SENSITIVE:
        if pattern.search(text):
            return GuardResult(False, f"Sensitive information detected in input: {label}.")

    for email in _EMAIL_RE.findall(text):
        domain = email.rsplit("@", 1)[-1].lower()
        if domain not in _SAFE_EMAIL_DOMAINS:
            return GuardResult(False, "Possible personal email address detected in input.")

    if os.getenv("AGENT_ENABLE_PII_GUARD", "").lower() in {"1", "true", "yes"}:
        pii_result = _check_presidio_pii(text)
        if not pii_result.passed:
            return pii_result

    return GuardResult(True)


def _check_presidio_pii(text: str) -> GuardResult:
    try:
        from presidio_analyzer import AnalyzerEngine
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "AGENT_ENABLE_PII_GUARD is enabled, but presidio-analyzer is not installed."
        ) from exc

    results = AnalyzerEngine().analyze(
        text=text,
        language="en",
        entities=_PRESIDIO_ENTITIES,
        score_threshold=0.5,
    )
    if results:
        found = sorted({result.entity_type for result in results})
        return GuardResult(False, f"PII detected in input: {', '.join(found)}.")
    return GuardResult(True)
