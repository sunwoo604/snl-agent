"""Prompt for converting a config document between JSON, YAML and TOML.

This path is only used when the input does not parse cleanly (so a stdlib
round-trip is impossible) or when the caller explicitly asks for the model.
"""

from . import clip

SYSTEM = (
    "You convert configuration documents between JSON, YAML and TOML. "
    "You reply with the converted document and nothing else: no preamble, no "
    "explanation, no markdown fences."
)

_RULES = """\
Rules:
- Preserve every key and value exactly. Do not add, drop, reorder or rename anything.
- Preserve types: numbers stay numbers, booleans stay booleans, strings stay strings.
- If the input is malformed, repair the syntax but never invent data.
- Output only the converted document, starting with its first character.
"""


def build(
    text: str,
    source: str,
    target: str,
    feedback: str | None = None,
) -> str:
    """Assemble the user prompt for a source → target conversion."""
    parts = [
        f"Convert the following {source.upper()} document to {target.upper()}.",
        _RULES,
        f"Input ({source}):\n{clip(text)}",
    ]
    if feedback:
        parts.append(
            f"Your previous answer was rejected: {feedback}\n"
            f"Return only a corrected {target.upper()} document."
        )
    parts.append(f"Output ({target}):")
    return "\n\n".join(parts)
