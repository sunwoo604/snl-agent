"""Command-line surface. Argument parsing and help text only — no logic.

Every command follows the same shape: collect input, call one task function,
print ``result.value``. Exit codes are uniform:

  0  verified output
  1  an error (bad input, Ollama unreachable, impossible conversion)
  2  best-effort output that never passed validation
"""

import json
import sys
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from typing import Annotated, Optional

import typer

from . import llm, usage
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


@app.command()
def stats(
    days: Annotated[
        Optional[int],
        typer.Option("--days", "-d", min=1, help="Window in days. Default: 7."),
    ] = 7,
    all_time: Annotated[
        bool, typer.Option("--all", help="Ignore --days and cover the whole log.")
    ] = False,
    as_json: Annotated[
        bool, typer.Option("--json", help="Machine-readable output.")
    ] = False,
) -> None:
    """Show what the local model has done for you: calls, tokens, pass rate.

    Use this for: checking whether routing work to snl-agent is paying off, or
    why it feels slow (high attempt counts mean the model keeps failing
    verification; consider a bigger model). Reads the local usage log only;
    never calls the model.

        snl-agent stats
        snl-agent stats --days 30 --json

    Set SNL_AGENT_USAGE=0 to stop recording.
    """
    summary = usage.summarize(None if all_time else days)
    if as_json:
        typer.echo(json.dumps(_stats_json(summary), indent=2))
    else:
        typer.echo(_stats_table(summary))


def _stats_json(summary: usage.Summary) -> dict:
    def row(s: usage.TaskStats) -> dict:
        return {
            "calls": s.calls,
            "prompt_tokens": s.prompt_tokens,
            "response_tokens": s.response_tokens,
            "runs": s.runs,
            "passed": s.passed,
            "pass_rate": s.pass_rate,
            "avg_attempts": s.avg_attempts,
            "avg_seconds_per_call": s.avg_seconds,
        }

    return {
        "days": summary.days,
        "total": row(summary.total),
        "tasks": {name: row(s) for name, s in sorted(summary.tasks.items())},
    }


def _stats_table(summary: usage.Summary) -> str:
    window = "all time" if summary.days is None else f"last {summary.days} days"
    if not summary.tasks:
        return f"No local-model usage recorded ({window})."

    def fmt(name: str, s: usage.TaskStats) -> str:
        rate = "-" if s.pass_rate is None else f"{s.pass_rate:.0%}"
        tries = "-" if s.avg_attempts is None else f"{s.avg_attempts:.1f}"
        secs = "-" if s.avg_seconds is None else f"{s.avg_seconds:.1f}s"
        return (
            f"{name:<12}{s.calls:>6}{s.prompt_tokens:>11,}{s.response_tokens:>10,}"
            f"{rate:>7}{tries:>10}{secs:>10}"
        )

    lines = [
        f"snl-agent usage ({window})",
        f"{'task':<12}{'calls':>6}{'tok in':>11}{'tok out':>10}{'pass':>7}{'attempts':>10}{'s/call':>10}",
    ]
    lines += [fmt(name, s) for name, s in sorted(summary.tasks.items())]
    if len(summary.tasks) > 1:
        lines.append(fmt("total", summary.total))
    return "\n".join(lines)


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
