# Contributing

## Development install

`install.sh` is for users. For working on the code, use an editable install:

```bash
python3 -m venv ~/.venvs/snl-agent
source ~/.venvs/snl-agent/bin/activate
pip install -e ".[dev]"
```

Requires Python 3.11+ (for `tomllib`).

> **macOS:** keep the virtualenv *outside* any iCloud-synced folder — Desktop
> and Documents are synced by default. iCloud sets the `hidden` flag on what it
> syncs and `site.addsitedir` skips hidden `.pth` files, so an editable install
> appears to succeed but `import snl_agent` fails. `~/.venvs` is a safe home.

To test `install.sh` itself against your working tree, without touching your
real installation:

```bash
SNL_AGENT_HOME=$(mktemp -d)/snl SNL_AGENT_REPO=$PWD sh install.sh
```

A local directory in `SNL_AGENT_REPO` is installed straight from disk instead
of being cloned, so this works with uncommitted changes.

## Tests

```bash
pytest
```

The suite mocks `llm.generate` throughout and never needs a running Ollama.
Keep it that way — a test that requires a live model is a test that will be
skipped.

## Layout

```
src/snl_agent/
├── cli.py        # argument parsing and help text ONLY
├── config.py     # env-backed defaults
├── llm.py        # the single place that talks to Ollama
├── verify.py     # run_with_retry + output cleanup helpers
├── prompts/      # one prompt module per task
└── tasks/        # one logic module per task, testable without the CLI
```

## Conventions

In priority order:

1. `cli.py` is argument parsing and help text **only**. Logic lives in `tasks/`.
2. Every HTTP call to Ollama goes through `llm.generate` in `llm.py`. Nowhere
   else.
3. Every task validates its own output and retries via `verify.run_with_retry`
   before returning. Tasks return a `RetryResult`, so the CLI can handle all of
   them identically.
4. Prefer determinism. If a task can be done correctly without the model, do
   that and use the model only for the part that genuinely needs it — see
   `tasks/convert.py`, which parses locally and calls the model only to repair
   input that will not parse.
5. Tests mock `llm.generate`. The suite must never require a live Ollama.
6. Command docstrings must open with a `Use this for:` line — that is what makes
   them discoverable to an agent reading `--help`.
7. Stdlib and tiny deps only. This is a personal tool; keep it lean.

Three rules hold the whole thing together: `cli.py` stays thin, all Ollama
access goes through `llm.py`, and every task validates its own output before
returning.

## Adding a task

A fixed four-step ritual:

1. `src/snl_agent/prompts/<task>.py` — a `SYSTEM` string and a
   `build(..., feedback=None)` function. Pure strings, no I/O.
2. `src/snl_agent/tasks/<task>.py` — clean the reply, validate it, and drive
   `run_with_retry`. Return a `RetryResult`.
3. `src/snl_agent/cli.py` — a thin command whose docstring opens with a
   `Use this for:` line, so an agent can route to it from `--help` alone.
4. `tests/test_<task>.py` — mock the LLM; test the validator and the retry.

## Not part of the package

`agent_snl.py` at the repo root is a standalone tool-calling prototype, not
part of the package.
