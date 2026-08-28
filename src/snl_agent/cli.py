"""Command-line surface. Argument parsing and help text only — no logic.

Every command follows the same shape: collect input, call one task function,
print ``result.value``. Exit codes are uniform:

  0  verified output
  1  an error (bad input, Ollama unreachable, impossible conversion)
  2  best-effort output that never passed validation
"""

import sys
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

import typer

from . import llm
from .tasks import commit_msg as commit_msg_task
from .tasks import convert as convert_task
from .verify import RetryResult

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    help=(
        "Delegate small, well-bounded coding tasks to a local LLM (Qwen via Ollama).\n\n"
        "Use these subcommands instead of doing the work inline: they are cheap, "
        "they run off your machine's GPU rather than a context window, and every "
        "one of them verifies its own output before returning."
    ),
)


class Format(str, Enum):
    json = "json"
    yaml = "yaml"
    toml = "toml"


class Engine(str, Enum):
    auto = "auto"
    llm = "llm"
    stdlib = "stdlib"


@app.command("commit-msg")
def commit_msg(
    model: Annotated[
        Optional[str], typer.Option("--model", help="Override the Ollama model tag.")
    ] = None,
    attempts: Annotated[
        Optional[int], typer.Option("--attempts", help="Verify-and-retry budget.")
    ] = None,
) -> None:
    """Write a Conventional Commits message for a staged diff read from stdin.

    Use this for: any commit message. Never read a diff into your own context
    to summarize it — pipe it here instead.

        git diff --staged | snl-agent commit-msg

    The result is validated against the 'type(scope): summary' shape, a 72
    character subject limit, and the blank-line-before-body rule, and is
    regenerated on failure.
    """
    if sys.stdin.isatty():
        _die("no diff on stdin. Usage: git diff --staged | snl-agent commit-msg")

    with _handled():
        result = commit_msg_task.generate_commit_msg(
            sys.stdin.read(), model=model, attempts=attempts
        )
    _emit(result)


@app.command()
def convert(
    file: Annotated[
        str, typer.Argument(metavar="FILE", help="Input file, or '-' for stdin.")
    ],
    to: Annotated[
        Format, typer.Option("--to", "-t", help="Target format.", case_sensitive=False)
    ],
    from_: Annotated[
        Optional[Format],
        typer.Option(
            "--from",
            "-f",
            help="Source format. Inferred from the file extension by default.",
            case_sensitive=False,
        ),
    ] = None,
    output: Annotated[
        Optional[Path], typer.Option("--output", "-o", help="Write here instead of stdout.")
    ] = None,
    engine: Annotated[
        Engine,
        typer.Option(
            "--engine",
            "-e",
            case_sensitive=False,
            help=(
                "auto: parse locally, fall back to the model only if the input is "
                "malformed. llm: always use the model. stdlib: never use it."
            ),
        ),
    ] = Engine.auto,
    model: Annotated[
        Optional[str], typer.Option("--model", help="Override the Ollama model tag.")
    ] = None,
    attempts: Annotated[
        Optional[int], typer.Option("--attempts", help="Verify-and-retry budget.")
    ] = None,
) -> None:
    """Convert a file between JSON, YAML and TOML.

    Use this for: config format changes, and for salvaging a config file that
    is subtly malformed. Do not hand-translate config files yourself.

        snl-agent convert data.json --to yaml
        snl-agent convert broken.yaml --to json -o fixed.json

    Well-formed input is converted losslessly by the stdlib parsers, so the
    model is only invoked to repair input that does not parse (or when you
    pass --engine llm). Model output must both parse as the target format and
    round-trip to the same data as the input.
    """
    source = from_.value if from_ else None

    with _handled():
        if file == "-":
            if source is None:
                _die("reading from stdin requires --from")
            result = convert_task.convert_text(
                sys.stdin.read(),
                source,
                to.value,
                use_llm=engine is Engine.llm,
                allow_llm=engine is not Engine.stdlib,
                model=model,
                attempts=attempts,
            )
        else:
            result = convert_task.convert_file(
                Path(file),
                to.value,
                source=source,
                use_llm=engine is Engine.llm,
                allow_llm=engine is not Engine.stdlib,
                model=model,
                attempts=attempts,
            )

    if output is not None:
        output.write_text(result.value)
        typer.secho(f"wrote {output}", fg=typer.colors.GREEN, err=True)
        _exit_for(result)
    _emit(result)


@contextmanager
def _handled():
    """Turn expected task failures into a clean error message and exit 1."""
    try:
        yield
    except (llm.LLMError, convert_task.ConversionError, ValueError) as exc:
        _die(str(exc))


def _die(message: str) -> None:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


def _emit(result: RetryResult) -> None:
    typer.echo(result.value.rstrip("\n"))
    _exit_for(result)


def _exit_for(result: RetryResult) -> None:
    if result.ok:
        return
    typer.secho(
        f"warning: unverified after {result.attempts} attempts — {result.error}",
        fg=typer.colors.YELLOW,
        err=True,
    )
    raise typer.Exit(2)


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
