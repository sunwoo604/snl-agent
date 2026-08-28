"""Prompt builders — one module per task. No network, no I/O, pure strings."""

from .. import config


def clip(text: str, limit: int | None = None) -> str:
    """Trim oversized input to fit the model's context, keeping head and tail.

    The middle of a large diff or file is usually the least informative part,
    so we keep the beginning (what changed first) and the end.
    """
    limit = config.MAX_INPUT_CHARS if limit is None else limit
    if len(text) <= limit:
        return text
    head = int(limit * 0.6)
    tail = limit - head
    omitted = len(text) - limit
    return f"{text[:head]}\n\n... [{omitted} characters omitted] ...\n\n{text[-tail:]}"
