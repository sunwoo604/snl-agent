"""Turn a staged git diff into a Conventional Commits message."""

import re

from .. import config, llm
from ..prompts import commit_msg as prompt
from ..verify import RetryResult, run_with_retry, strip_code_fence, strip_wrapping_quotes

TYPES = (
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
)

MAX_SUBJECT = 72

SUBJECT_RE = re.compile(
    rf"^(?:{'|'.join(TYPES)})(?:\([^()\n]+\))?!?: \S.*$"
)

_LABEL = r"(?:message|commit message|answer|output)"
_LABEL_PREFIX_RE = re.compile(rf"^{_LABEL}\s*:\s*", re.IGNORECASE)
_LABEL_ONLY_RE = re.compile(rf"^{_LABEL}\s*:?\s*$", re.IGNORECASE)


def clean(raw: str) -> str:
    """Strip the wrappers a chat model tends to add around its answer."""
    text = strip_code_fence(raw)

    lines = text.splitlines()
    # Drop leading blank or label-only lines ("Message:").
    while lines and (not lines[0].strip() or _LABEL_ONLY_RE.match(lines[0].strip())):
        lines.pop(0)
    if lines:
        lines[0] = _LABEL_PREFIX_RE.sub("", lines[0].strip())
    text = "\n".join(lines).strip()

    if "\n" not in text:
        text = strip_wrapping_quotes(text)
    return text.strip()


def validate_message(message: str) -> tuple[bool, str]:
    """Check the Conventional Commits shape. Returns ``(ok, reason)``."""
    if not message.strip():
        return False, "the message was empty"

    lines = message.splitlines()
    subject = lines[0].strip()

    if not SUBJECT_RE.match(subject):
        return False, (
            f"the subject {subject!r} does not match 'type(scope): summary'; "
            f"type must be one of {', '.join(TYPES)}"
        )
    if len(subject) > MAX_SUBJECT:
        return False, (
            f"the subject is {len(subject)} characters, the limit is {MAX_SUBJECT}"
        )
    if subject.endswith("."):
        return False, "the subject must not end with a period"
    if len(lines) > 1 and lines[1].strip():
        return False, "a body must be separated from the subject by a blank line"
    return True, ""


def generate_commit_msg(
    diff: str,
    *,
    model: str | None = None,
    attempts: int | None = None,
) -> RetryResult:
    """Generate and verify a commit message for ``diff``.

    Returns a :class:`RetryResult` whose ``value`` is the message. ``ok`` is
    False when every attempt failed validation and the best effort is returned.
    """
    if not diff.strip():
        raise ValueError("the diff is empty — nothing is staged")

    def attempt(feedback: str | None) -> str:
        raw = llm.generate(
            prompt.build(diff, feedback),
            model=model,
            system=prompt.SYSTEM,
        )
        return clean(raw)

    return run_with_retry(
        attempt,
        validate_message,
        attempts=config.ATTEMPTS if attempts is None else attempts,
    )
