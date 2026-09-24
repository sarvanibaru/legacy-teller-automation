from __future__ import annotations

import re

REDACTED = "[REDACTED]"

# Field names that are always redacted regardless of their value, matched
# case-insensitively and matched as a substring so "user_password" and
# "PasswordConfirm" both get caught, not just an exact "password" key.
SENSITIVE_KEY_SUBSTRINGS = [
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "ssn",
    "social_security",
    "credit_card",
    "card_number",
    "cvv",
    "pin",
]

# Patterns that indicate sensitive content by shape, independent of what
# field they happen to be in -- this is the safety net for values that
# ended up somewhere with an innocent-looking name.
PATTERNS = [
    # US Social Security Number: 123-45-6789
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    # Credit card-like: 13 to 16 digits, optionally grouped with spaces/dashes
    re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    # Anthropic API keys
    re.compile(r"sk-ant-[A-Za-z0-9\-_]+"),
    # Generic bearer tokens
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*"),
]


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(substr in lowered for substr in SENSITIVE_KEY_SUBSTRINGS)


def redact_text(text: str) -> str:
    """Applies pattern-based redaction to a plain string. Use this for any
    free-text value (log messages, extracted page text) that might contain
    sensitive content regardless of context."""
    result = text
    for pattern in PATTERNS:
        result = pattern.sub(REDACTED, result)
    return result


def redact_value(value):
    """Recursively redacts a value of any shape (dict, list, str, or a
    plain scalar). Dict keys matching a sensitive-name substring are
    redacted outright, regardless of their value's shape; everything else
    is recursed into or pattern-checked."""
    if isinstance(value, dict):
        return {
            key: (REDACTED if _is_sensitive_key(key) else redact_value(val))
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
