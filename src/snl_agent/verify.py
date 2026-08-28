"""Shared verify-and-retry machinery.

Every task in this package produces a *checkable* output. The contract is
always the same: generate a candidate, validate it, and if it fails, feed the
reason back into the next attempt. After the budget is exhausted the best
effort is returned with ``ok=False`` so the caller can warn rather than lie.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Callable


class Invalid(Exception):
    """Raise from a validator to reject a candidate with an explanation."""


@dataclass
class RetryResult:
    """Outcome of :func:`run_with_retry`."""

    value: Any
    ok: bool
    attempts: int
    errors: list[str] = field(default_factory=list)

    @property
    def error(self) -> str | None:
        """The reason the final candidate was rejected, if it was."""
        return self.errors[-1] if self.errors and not self.ok else None


def run_with_retry(
    fn: Callable[[str | None], Any],
    validate: Callable[[Any], Any],
    attempts: int = 3,
) -> RetryResult:
    """Call ``fn`` until ``validate`` accepts its result.

    ``fn`` receives the previous failure message (``None`` on the first
    attempt) so it can tighten its prompt. ``validate`` may return ``True`` /
    ``False``, a ``(ok, message)`` pair, ``None`` for success, or raise
    :class:`Invalid`.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    errors: list[str] = []
    value: Any = None
    feedback: str | None = None

    for attempt in range(1, attempts + 1):
        value = fn(feedback)
        ok, message = _normalize(validate, value)
        if ok:
            return RetryResult(value=value, ok=True, attempts=attempt, errors=errors)
        errors.append(message)
        feedback = message

    return RetryResult(value=value, ok=False, attempts=attempts, errors=errors)


def _normalize(validate: Callable[[Any], Any], value: Any) -> tuple[bool, str]:
    try:
        outcome = validate(value)
    except Invalid as exc:
        return False, str(exc) or "rejected by validator"

    if outcome is None or outcome is True:
        return True, ""
    if outcome is False:
        return False, "output failed validation"
    if isinstance(outcome, tuple) and len(outcome) == 2:
        ok, message = outcome
        return bool(ok), "" if ok else str(message)
    raise TypeError(f"validator returned an unsupported value: {outcome!r}")


_FENCE = re.compile(
    r"\A\s*```[^\n]*\n(?P<body>.*?)\n?```\s*\Z",
    re.DOTALL,
)


def strip_code_fence(text: str) -> str:
    """Unwrap a single ```-fenced block, if the whole output is one."""
    match = _FENCE.match(text)
    return match.group("body") if match else text.strip()


def strip_wrapping_quotes(text: str) -> str:
    """Drop matching quotes the model wrapped around a one-line answer."""
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'`":
        return text[1:-1].strip()
    return text
