"""Smoke tests for the CLI surface: wiring, help discoverability, exit codes."""

import json

import pytest
import yaml
from typer.testing import CliRunner

from snl_agent import llm
from snl_agent.cli import app

runner = CliRunner()

DIFF = "diff --git a/a.py b/a.py\n@@ -1 +1,2 @@\n+x = 1\n"


def test_help_lists_every_subcommand():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("commit-msg", "convert", "stats"):
        assert command in result.stdout


@pytest.mark.parametrize("command", ["commit-msg", "convert", "stats"])
def test_each_command_has_its_own_help_saying_when_to_use_it(command):
    result = runner.invoke(app, [command, "--help"])
    assert result.exit_code == 0
    assert "Use this for" in result.stdout


def test_commit_msg_prints_the_message(fake_llm):
    fake_llm("feat(a): add x")
    result = runner.invoke(app, ["commit-msg"], input=DIFF)

    assert result.exit_code == 0
    assert result.stdout.strip() == "feat(a): add x"


def test_commit_msg_exits_2_when_unverified(fake_llm):
    fake_llm("not a commit message")
    result = runner.invoke(app, ["commit-msg", "--attempts", "1"], input=DIFF)

    assert result.exit_code == 2
    assert "not a commit message" in result.stdout
    assert "unverified" in result.stderr


def test_convert_writes_to_stdout(tmp_path):
    src = tmp_path / "d.json"
    src.write_text('{"a": 1}')

    result = runner.invoke(app, ["convert", str(src), "--to", "yaml"])

    assert result.exit_code == 0
    assert yaml.safe_load(result.stdout) == {"a": 1}


def test_convert_writes_to_a_file(tmp_path):
    src = tmp_path / "d.json"
    src.write_text('{"a": 1}')
    dst = tmp_path / "d.yaml"

    result = runner.invoke(app, ["convert", str(src), "-t", "yaml", "-o", str(dst)])

    assert result.exit_code == 0
    assert yaml.safe_load(dst.read_text()) == {"a": 1}


def test_convert_reads_stdin_with_an_explicit_source():
    result = runner.invoke(app, ["convert", "-", "-f", "json", "-t", "yaml"], input='{"a": 1}')

    assert result.exit_code == 0
    assert yaml.safe_load(result.stdout) == {"a": 1}


def test_convert_stdin_without_from_is_an_error():
    result = runner.invoke(app, ["convert", "-", "-t", "yaml"], input="{}")

    assert result.exit_code == 1
    assert "requires --from" in result.stderr


def test_convert_stdlib_engine_refuses_to_call_the_model(tmp_path, fake_llm):
    fake = fake_llm("{}")
    src = tmp_path / "d.json"
    src.write_text("{broken")

    result = runner.invoke(app, ["convert", str(src), "-t", "yaml", "-e", "stdlib"])

    assert result.exit_code == 1
    assert fake.call_count == 0


def test_unreachable_ollama_is_a_clean_error(monkeypatch):
    def boom(*args, **kwargs):
        raise llm.LLMError("Cannot reach Ollama at http://localhost:11434.")

    monkeypatch.setattr(llm, "generate", boom)
    result = runner.invoke(app, ["commit-msg"], input=DIFF)

    assert result.exit_code == 1
    assert "Cannot reach Ollama" in result.stderr
    assert "Traceback" not in result.stderr


def test_no_args_shows_help():
    result = runner.invoke(app, [])
    assert result.exit_code != 0
    assert "commit-msg" in result.stdout


def test_json_round_trip_through_the_cli(tmp_path):
    src = tmp_path / "d.json"
    payload = {"server": {"host": "localhost", "port": 8080}, "tags": ["a"]}
    src.write_text(json.dumps(payload))

    as_toml = runner.invoke(app, ["convert", str(src), "-t", "toml"])
    assert as_toml.exit_code == 0

    toml_file = tmp_path / "d.toml"
    toml_file.write_text(as_toml.stdout)
    back = runner.invoke(app, ["convert", str(toml_file), "-t", "json"])

    assert back.exit_code == 0
    assert json.loads(back.stdout) == payload
