# snl-agent

Delegate small, well-bounded coding tasks to a local LLM (Qwen via Ollama)
instead of burning a large model's context on them.

The idea: commit messages and format conversions are cheap, repetitive,
context-light work. Running them on your own GPU keeps a coding agent like
Claude Code lean and fast, and keeps your source out of a remote context
window. Every task here has a **checkable** output and a verify-and-retry
loop, so "small local model" doesn't mean "unreliable".

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/OWNER/snl-agent/main/install.sh | sh
```

Everything lands in one directory:

```
~/.snl-agent/
├── venv/                 the virtualenv, owned by the installer
├── bin/snl-agent         the command
└── data/                 your data — never touched by install or uninstall
```

The installer links `snl-agent` into `~/.local/bin` when that is already on
your `PATH`; otherwise it prints the one line to add. It never edits your
shell config. Re-running it is how you upgrade.

Requires **Python 3.11+** (for `tomllib`) and `git`. The installer finds a
suitable Python itself and tells you what to install if there isn't one.

Prefer a Python CLI manager? The packaging supports them directly:

```bash
uv tool install git+https://github.com/OWNER/snl-agent
pipx install git+https://github.com/OWNER/snl-agent
```

### Uninstall

```bash
sh uninstall.sh              # remove the program, keep ~/.snl-agent/data
sh uninstall.sh --purge      # remove everything
```

## Ollama setup

```bash
brew install ollama            # or https://ollama.com/download
ollama serve                   # leave running
ollama pull qwen3.6:35b-a3b-coding-bf16
```

Check it:

```bash
curl -s http://localhost:11434/api/tags
```

> **On model size.** The default tag is a 35B model at bf16 — roughly 70 GB to
> download and hold in memory. If that is more machine than you have, pull
> something smaller and point `MODEL` at it:
>
> ```bash
> ollama pull qwen2.5-coder:7b
> export MODEL=qwen2.5-coder:7b
> ```
>
> Every task here validates its own output, so a smaller model degrades into
> "more retries", not "wrong answers accepted".

## Commands

Run `snl-agent --help`, or `snl-agent <command> --help`, for the full surface.

### `commit-msg`

Reads a staged diff from stdin, writes a Conventional Commits message.

```bash
git diff --staged | snl-agent commit-msg
git commit -m "$(git diff --staged | snl-agent commit-msg)"
```

**Verified:** the subject matches `type(scope): summary`, the type is a real
conventional type, the subject is ≤72 characters with no trailing period, and
any body is separated by a blank line. A rejected message is regenerated with
the reason fed back to the model.

### `convert`

Converts a document between JSON, YAML and TOML.

```bash
snl-agent convert data.json --to yaml
snl-agent convert config.toml -t json -o config.json
cat data.json | snl-agent convert - --from json --to yaml
snl-agent convert broken.yaml --to json          # repairs, then converts
```

**Engine.** Well-formed input is converted by the stdlib parsers — instant,
lossless, and incapable of inventing data. The model is only invoked when the
input does not parse, which is the case a parser genuinely cannot handle.
Override with `--engine llm` (always use the model) or `--engine stdlib`
(never use it; malformed input becomes an error).

**Verified:** model output must parse as the target format *and*, when the
input was parseable, round-trip to exactly the same data.

## Using it with Claude Code

This is what the tool is really for. Drop a routing policy in your project's
`CLAUDE.md` and the agent will reach for these commands instead of pulling the
work into its own context:

```markdown
| If you are about to…                        | Run instead                          |
| ------------------------------------------- | ------------------------------------ |
| Read a staged diff to write a commit message | `git diff --staged \| snl-agent commit-msg` |
| Hand-translate JSON ↔ YAML ↔ TOML           | `snl-agent convert FILE --to FORMAT` |
| Fix a config file that fails to parse        | `snl-agent convert FILE --to FORMAT` |
```

Every command's `--help` opens with a `Use this for:` line, so an agent can
route correctly from `--help` alone. This repo's own [CLAUDE.md](CLAUDE.md) is
a worked example, including the rule that matters most: **don't** route
anything needing repo-wide context or design judgement here. The local model
only ever sees what you pipe into it.

## Configuration

All optional, read from the environment:

| Variable | Default | Meaning |
| --- | --- | --- |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama base URL |
| `MODEL` | `qwen3.6:35b-a3b-coding-bf16` | Model tag |
| `SNL_AGENT_TIMEOUT` | `180` | Seconds per generation |
| `SNL_AGENT_ATTEMPTS` | `3` | Verify-and-retry budget |
| `SNL_AGENT_TEMPERATURE` | `0.2` | Sampling temperature |
| `SNL_AGENT_MAX_INPUT_CHARS` | `12000` | Input clipped to this, head and tail kept |

The installer also reads `SNL_AGENT_HOME` (default `~/.snl-agent`),
`SNL_AGENT_REPO` and `SNL_AGENT_REF`.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Output produced and verified |
| `1` | Error — bad input, unreachable Ollama, impossible conversion |
| `2` | Best-effort output printed, but it never passed validation (warning on stderr) |

Exit code 2 still prints a result on stdout. In a script, treat it as "look at
this before using it".

## Troubleshooting

**`Cannot reach Ollama`** — start it with `ollama serve`, and check
`curl -s http://localhost:11434/api/tags`.

**HTTP 404 from Ollama** — the model tag isn't pulled. `ollama pull <tag>`.

**`snl-agent: command not found` after installing** — `~/.snl-agent/bin` isn't
on your `PATH`. Re-run `install.sh`; it prints the exact line to add.

**macOS: `ModuleNotFoundError: No module named 'snl_agent'` after a
`pip install -e .`** — the virtualenv is inside an iCloud-synced folder
(Desktop and Documents are synced by default). iCloud sets the `hidden` flag on
what it syncs, and `site.addsitedir` silently skips hidden `.pth` files, so the
editable install appears to succeed but imports fail. Confirm with
`ls -lO <venv>/lib/python3.*/site-packages/*.pth`; a stray `lib 2` directory in
the venv is the same problem. Rebuild the venv somewhere unsynced. This only
affects editable dev installs — `install.sh` puts its venv in `~/.snl-agent`,
which is not synced.

## Licensing

**Not yet licensed.** No `LICENSE` file has been added, which means no rights
are granted: you may read this code, but not use, copy, modify, or distribute
it. A permissive license is planned — until then, treat it as all rights
reserved.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development install, the module
layout, and the four-step ritual for adding a task.
