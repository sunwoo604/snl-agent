import json
from pathlib import Path

import pytest
import tomllib
import yaml

from snl_agent.tasks.convert import (
    ConversionError,
    convert_file,
    convert_text,
    format_from_path,
    parse,
    serialize,
)

DATA = {
    "name": "widgets",
    "version": "1.2.3",
    "debug": False,
    "retries": 3,
    "tags": ["a", "b"],
    "server": {"host": "localhost", "port": 8080},
}

JSON_TEXT = json.dumps(DATA, indent=2)


@pytest.mark.parametrize("target", ["json", "yaml", "toml"])
def test_stdlib_round_trip_preserves_data(target):
    result = convert_text(JSON_TEXT, "json", target)

    assert result.ok
    assert result.attempts == 0, "well-formed input must not call the model"
    assert parse(result.value, target) == DATA


def test_yaml_to_toml_and_back():
    as_yaml = convert_text(JSON_TEXT, "json", "yaml").value
    as_toml = convert_text(as_yaml, "yaml", "toml").value
    assert tomllib.loads(as_toml) == DATA


def test_no_model_call_for_valid_input(fake_llm):
    fake = fake_llm("should not be used")
    convert_text(JSON_TEXT, "json", "yaml")
    assert fake.call_count == 0


@pytest.mark.parametrize(
    "name, expected",
    [("a.json", "json"), ("a.yaml", "yaml"), ("a.yml", "yaml"), ("A.TOML", "toml")],
)
def test_format_inferred_from_extension(name, expected):
    assert format_from_path(Path(name)) == expected


def test_unknown_extension_is_an_error():
    with pytest.raises(ConversionError, match="cannot infer"):
        format_from_path(Path("data.ini"))


def test_unknown_format_is_an_error():
    with pytest.raises(ConversionError, match="unknown format"):
        convert_text("{}", "json", "xml")


def test_toml_requires_a_top_level_table():
    with pytest.raises(ConversionError, match="top level"):
        convert_text("[1, 2]", "json", "toml")


def test_values_toml_cannot_represent_are_reported():
    with pytest.raises(ConversionError, match="cannot be represented as TOML"):
        convert_text('{"a": null}', "json", "toml")


def test_convert_file_reads_and_infers(tmp_path):
    src = tmp_path / "data.json"
    src.write_text(JSON_TEXT)

    result = convert_file(src, "yaml")

    assert result.ok
    assert yaml.safe_load(result.value) == DATA


def test_missing_file_is_an_error(tmp_path):
    with pytest.raises(ConversionError, match="no such file"):
        convert_file(tmp_path / "nope.json", "yaml")


# --- the model-backed repair path -------------------------------------------

MALFORMED = '{"name": "widgets", "port": 8080,}'  # trailing comma


def test_malformed_input_falls_back_to_the_model(fake_llm):
    fake = fake_llm('{"name": "widgets", "port": 8080}')
    result = convert_text(MALFORMED, "json", "json")

    assert result.ok
    assert fake.call_count == 1
    assert json.loads(result.value) == {"name": "widgets", "port": 8080}


def test_malformed_input_is_an_error_when_the_model_is_disabled():
    with pytest.raises(ConversionError, match="not valid json"):
        convert_text(MALFORMED, "json", "yaml", allow_llm=False)


def test_model_output_must_parse_as_the_target(fake_llm):
    fake = fake_llm("this is not yaml: [unclosed", "name: widgets\nport: 8080\n")
    result = convert_text(MALFORMED, "json", "yaml")

    assert result.ok
    assert result.attempts == 2
    assert "rejected" in fake.prompts[1]


def test_forced_model_output_must_match_the_input_data(fake_llm):
    # Valid YAML, but the model dropped a key — must be rejected.
    fake = fake_llm("name: widgets\n", yaml.safe_dump(DATA, sort_keys=False))
    result = convert_text(JSON_TEXT, "json", "yaml", use_llm=True)

    assert result.ok
    assert result.attempts == 2
    assert "does not match the input data" in fake.prompts[1]
    assert yaml.safe_load(result.value) == DATA


def test_best_effort_returned_when_the_model_never_succeeds(fake_llm):
    fake = fake_llm("still: not: valid: yaml: [")
    result = convert_text(MALFORMED, "json", "yaml", attempts=2)

    assert not result.ok
    assert result.attempts == 2
    assert fake.call_count == 2


def test_model_output_is_unfenced(fake_llm):
    fake_llm("```yaml\nname: widgets\nport: 8080\n```")
    result = convert_text(MALFORMED, "json", "yaml")

    assert result.ok
    assert yaml.safe_load(result.value) == {"name": "widgets", "port": 8080}


def test_serialize_rejects_unknown_format():
    with pytest.raises(ConversionError, match="unknown format"):
        serialize({}, "ini")
