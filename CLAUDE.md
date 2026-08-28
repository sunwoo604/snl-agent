# CLAUDE.md — routing policy for this repo

`snl-agent` exists so that small, checkable tasks run on a local model instead
of in your context window. **Prefer these subcommands over doing the work
inline.** They are faster than reading the input yourself, they cost no
context, and each one verifies its own output before returning.

## Route to snl-agent

| If you are about to… | Run instead |
| --- | --- |
| Read a staged diff to write a commit message | `git diff --staged \| snl-agent commit-msg` |
| Hand-translate JSON ↔ YAML ↔ TOML | `snl-agent convert FILE --to FORMAT` |
| Fix a config file that fails to parse | `snl-agent convert FILE --to FORMAT` |

Discover the full surface with `snl-agent --help` and
`snl-agent <command> --help`. Each command's help opens with a "Use this for:"
line — that line is the routing rule.

### Examples

```bash
# Commit message — never read the diff into context first.
git commit -m "$(git diff --staged | snl-agent commit-msg)"

# Format conversion, straight to a file.
snl-agent convert pyproject.toml --to json -o pyproject.json

# Repair a config file that will not parse, in place of hand-editing it.
snl-agent convert broken.yaml --to yaml -o fixed.yaml
```

## Reading the result

- **Exit 0** — output is verified. Use it.
- **Exit 1** — an error on stderr. Ollama may be down (`ollama serve`); fall
  back to doing the task yourself.
- **Exit 2** — output printed but never passed validation. Read it before
  using it; this is the one case where you should apply your own judgement.

## Do not route to snl-agent

Anything needing repo-wide context, judgement about design, or multi-file
edits. The local model sees only what you pipe into it. If a task needs to
know why the code is the way it is, keep it.

## Working on this repo

Conventions, in priority order:

1. `cli.py` is argument parsing and help text **only**. Logic lives in
   `tasks/`.
2. Every HTTP call to Ollama goes through `llm.generate` in `llm.py`. Nowhere
   else.
3. Every task validates its own output and retries via
   `verify.run_with_retry` before returning. Tasks return a `RetryResult`, so
   the CLI can handle all of them identically.
4. Prefer determinism. If a task can be done correctly without the model, do
   that and use the model only for the part that genuinely needs it — see
   `tasks/convert.py`, which parses locally and calls the model only to repair
   input that will not parse.
5. Tests mock `llm.generate`. The suite must never require a live Ollama.
6. Command docstrings must open with a "Use this for:" line — that is what
   makes them discoverable to an agent reading `--help`.
7. Stdlib and tiny deps only. This is a personal tool; keep it lean.

Adding a task is a four-step ritual: prompt in `prompts/`, logic in `tasks/`,
command in `cli.py`, test in `tests/`. See the README for details.
