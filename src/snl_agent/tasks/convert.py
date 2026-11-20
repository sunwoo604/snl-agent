"""Convert a config document between JSON, YAML and TOML.

The stdlib can do this losslessly whenever the input parses, so that is the
default path: it is instant and cannot corrupt data. The model is used only
where it adds something a parser cannot — repairing a malformed document — or
when the caller forces it with ``use_llm``. Even then the result must parse as
the target format *and* round-trip to the same data as the input.
"""

import json
import tomllib
from pathlib import Path

import tomli_w
import yaml

from .. import config, llm
from ..prompts import convert as prompt
from ..verify import RetryResult, run_with_retry, strip_code_fence

FORMATS = ("json", "yaml", "toml")

_EXTENSIONS = {
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
}


class ConversionError(Exception):
    """The document could not be converted."""


def format_from_path(path: Path) -> str:
    """Infer a format from a filename extension."""
    fmt = _EXTENSIONS.get(path.suffix.lower())
    if fmt is None:
        raise ConversionError(
            f"cannot infer a format from {path.name!r}; "
            f"pass --from explicitly (one of {', '.join(FORMATS)})"
        )
    return fmt


def parse(text: str, fmt: str) -> object:
    """Parse ``text`` as ``fmt``, raising :class:`ConversionError` on failure."""
    _check_format(fmt)
    try:
        if fmt == "json":
            return json.loads(text)
        if fmt == "yaml":
            return yaml.safe_load(text)
        return tomllib.loads(text)
    except (json.JSONDecodeError, yaml.YAMLError, tomllib.TOMLDecodeError) as exc:
        raise ConversionError(f"input is not valid {fmt}: {exc}") from exc


def serialize(data: object, fmt: str) -> str:
    """Render ``data`` as ``fmt``."""
    _check_format(fmt)
    if fmt == "json":
        return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if fmt == "yaml":
        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    if not isinstance(data, dict):
        raise ConversionError(
            "TOML requires a table at the top level, but the document is "
            f"a {type(data).__name__}"
        )
    try:
        return tomli_w.dumps(data)
    except (TypeError, ValueError) as exc:
        raise ConversionError(
            f"this document cannot be represented as TOML: {exc}"
        ) from exc


def convert_text(
    text: str,
    source: str,
    target: str,
    *,
    use_llm: bool = False,
    allow_llm: bool = True,
    model: str | None = None,
    attempts: int | None = None,
) -> RetryResult:
    """Convert ``text`` from ``source`` to ``target``.

    Uses the stdlib round-trip unless ``use_llm`` is set. If the input does not
    parse, falls back to the model to repair it (unless ``allow_llm`` is False).
    ``attempts == 0`` in the result means no model call was needed.
    """
    _check_format(source)
    _check_format(target)

    data: object = None
    parse_error: ConversionError | None = None
    try:
        data = parse(text, source)
    except ConversionError as exc:
        parse_error = exc

    if parse_error is None and not use_llm:
        return RetryResult(value=serialize(data, target), ok=True, attempts=0)

    if not allow_llm:
        raise parse_error or ConversionError("the model is disabled (--no-llm)")

    return _convert_with_llm(
        text,
        source,
        target,
        expected=data,
        have_expected=parse_error is None,
        model=model,
        attempts=config.ATTEMPTS if attempts is None else attempts,
    )


def _convert_with_llm(
    text: str,
    source: str,
    target: str,
    *,
    expected: object,
    have_expected: bool,
    model: str | None,
    attempts: int,
) -> RetryResult:
    def attempt(feedback: str | None) -> str:
        raw = llm.generate(
            prompt.build(text, source, target, feedback),
            model=model,
            system=prompt.SYSTEM,
            task="convert",
        )
        return strip_code_fence(raw).strip() + "\n"

    def validate(candidate: str) -> tuple[bool, str]:
        try:
            produced = parse(candidate, target)
        except ConversionError as exc:
            return False, str(exc)
        if have_expected and produced != expected:
            return False, (
                "the output parses but does not match the input data; "
                "keep every key and value identical"
            )
        return True, ""

    return run_with_retry(attempt, validate, attempts=attempts, task="convert")


def convert_file(
    path: Path,
    target: str,
    *,
    source: str | None = None,
    **kwargs,
) -> RetryResult:
    """Read ``path`` and convert its contents to ``target``."""
    if not path.is_file():
        raise ConversionError(f"no such file: {path}")
    source = source or format_from_path(path)
    return convert_text(path.read_text(), source, target, **kwargs)


def _check_format(fmt: str) -> None:
    if fmt not in FORMATS:
        raise ConversionError(
            f"unknown format {fmt!r}; expected one of {', '.join(FORMATS)}"
        )
