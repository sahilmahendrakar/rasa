import argparse
import os
import re
from pathlib import Path
from unittest.mock import Mock
import pytest
from collections import namedtuple
from typing import Callable, Text

from _pytest.fixtures import FixtureRequest
from _pytest.monkeypatch import MonkeyPatch
from _pytest.pytester import RunResult
from rasa.cli import data
from rasa.shared.constants import ASSISTANT_ID_KEY, LATEST_TRAINING_DATA_FORMAT_VERSION
from rasa.shared.importers.importer import TrainingDataImporter
from rasa.shared.nlu.training_data.formats import RasaYAMLReader
from rasa.utils.common import EXPECTED_WARNINGS
from rasa.validator import Validator
import rasa.shared.utils.io

from tests.cli.conftest import RASA_EXE


def test_data_split_nlu(run_in_simple_project: Callable[..., RunResult]):
    responses_yml = (
        "responses:\n"
        "  chitchat/ask_name:\n"
        "  - text: my name is Sara, Rasa's documentation bot!\n"
        "  chitchat/ask_weather:\n"
        "  - text: the weather is great!\n"
    )

    with open("data/responses.yml", "w") as f:
        f.write(responses_yml)

    run_in_simple_project(
        "data",
        "split",
        "nlu",
        "-u",
        "data/nlu.yml",
        "--training-fraction",
        "0.75",
        "--random-seed",
        "12345",
    )

    folder = Path("train_test_split")
    assert folder.exists()

    nlu_files = [folder / "test_data.yml", folder / "training_data.yml"]
    nlg_files = [folder / "nlg_test_data.yml", folder / "nlg_training_data.yml"]
    for yml_file in nlu_files:
        assert yml_file.exists(), f"{yml_file} file does not exist"
        nlu_data = rasa.shared.utils.io.read_yaml_file(yml_file)
        assert "version" in nlu_data
        assert nlu_data.get("nlu")

    for yml_file in nlg_files:
        assert yml_file.exists(), f"{yml_file} file does not exist"


def test_data_convert_nlu_json(run_in_simple_project: Callable[..., RunResult]):

    result = run_in_simple_project(
        "data",
        "convert",
        "nlu",
        "--data",
        "data/nlu.yml",
        "--out",
        "out_nlu_data.json",
        "-f",
        "json",
    )

    assert "NLU data in Rasa JSON format is deprecated" in str(result.stderr)
    assert os.path.exists("out_nlu_data.json")


def test_data_convert_nlu_yml(
    run: Callable[..., RunResult], tmp_path: Path, request: FixtureRequest
):

    target_file = tmp_path / "out.yml"

    # The request rootdir is required as the `testdir` fixture in `run` changes the
    # working directory
    test_data_dir = Path(request.config.rootdir, "data", "examples", "rasa")
    source_file = (test_data_dir / "demo-rasa.json").absolute()
    result = run(
        "data",
        "convert",
        "nlu",
        "--data",
        str(source_file),
        "--out",
        str(target_file),
        "-f",
        "yaml",
    )

    assert result.ret == 0
    assert target_file.exists()

    actual_data = RasaYAMLReader().read(target_file)
    expected = RasaYAMLReader().read(test_data_dir / "demo-rasa.yml")

    assert len(actual_data.training_examples) == len(expected.training_examples)
    assert len(actual_data.entity_synonyms) == len(expected.entity_synonyms)
    assert len(actual_data.regex_features) == len(expected.regex_features)
    assert len(actual_data.lookup_tables) == len(expected.lookup_tables)
    assert actual_data.entities == expected.entities


def test_data_split_help(run: Callable[..., RunResult]):
    output = run("data", "split", "nlu", "--help")

    help_text = f"""usage: {RASA_EXE} data split nlu [-h] [-v] [-vv] [--quiet]\n
                           [--logging-config-file LOGGING_CONFIG_FILE]\n
                           [-u NLU] [--training-fraction TRAINING_FRACTION]\n
                           [--random-seed RANDOM_SEED] [--out OUT]"""

    lines = help_text.split("\n")
    # expected help text lines should appear somewhere in the output
    printed_help = set(output.outlines)
    for line in lines:
        assert line in printed_help


def test_data_convert_help(run: Callable[..., RunResult]):
    output = run("data", "convert", "nlu", "--help")

    help_text = f"""usage: {RASA_EXE} data convert nlu [-h] [-v] [-vv] [--quiet]\n
                           [--logging-config-file LOGGING_CONFIG_FILE]\n
                           [-f {"{json,yaml}"}] [--data DATA [DATA ...]]"""

    lines = help_text.split("\n")
    # expected help text lines should appear somewhere in the output
    printed_help = {line.strip() for line in output.outlines}
    for line in lines:
        assert line.strip() in printed_help


def test_data_validate_help(run: Callable[..., RunResult]):
    output = run("data", "validate", "--help")

    help_text = f"""usage: {RASA_EXE} data validate [-h] [-v] [-vv] [--quiet]
                          [--logging-config-file LOGGING_CONFIG_FILE]
                          [--max-history MAX_HISTORY] [-c CONFIG]
                          [--fail-on-warnings] [-d DOMAIN]
                          [--data DATA [DATA ...]]
                          {{stories}} ..."""

    lines = help_text.split("\n")
    # expected help text lines should appear somewhere in the output
    printed_help = {line.strip() for line in output.outlines}
    for line in lines:
        assert line.strip() in printed_help


def test_data_migrate_help(run: Callable[..., RunResult]):
    output = run("data", "migrate", "--help")
    printed_help = set(output.outlines)

    help_text = f"""usage: {RASA_EXE} data migrate [-h] [-v] [-vv] [--quiet]
                          [--logging-config-file LOGGING_CONFIG_FILE]
                          [-d DOMAIN] [--out OUT]"""
    lines = help_text.split("\n")
    # expected help text lines should appear somewhere in the output
    printed_help = {line.strip() for line in output.outlines}
    for line in lines:
        assert line.strip() in printed_help


def test_data_validate_stories_with_max_history_zero(monkeypatch: MonkeyPatch):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(help="Rasa commands")
    data.add_subparser(subparsers, parents=[])

    args = parser.parse_args(
        [
            "data",
            "validate",
            "stories",
            "--data",
            "data/test_moodbot/data",
            "--max-history",
            0,
            "--config",
            "data/test_moodbot/config.yml",
        ]
    )

    def mock_from_importer(importer: TrainingDataImporter) -> Validator:
        return Mock()

    monkeypatch.setattr("rasa.validator.Validator.from_importer", mock_from_importer)

    with pytest.raises(argparse.ArgumentTypeError):
        data.validate_files(args)


@pytest.mark.parametrize(
    ("file_type", "data_type"), [("stories", "story"), ("rules", "rule")]
)
def test_validate_files_action_not_found_invalid_domain(
    file_type: Text, data_type: Text, tmp_path: Path
):
    file_name = tmp_path / f"{file_type}.yml"
    file_name.write_text(
        f"""
        version: "{LATEST_TRAINING_DATA_FORMAT_VERSION}"
        {file_type}:
        - {data_type}: test path
          steps:
          - intent: goodbye
          - action: action_test
        """
    )
    args = {
        "domain": "data/test_moodbot/domain.yml",
        "data": [file_name],
        "max_history": None,
        "config": "data/test_config/config_defaults.yml",
    }
    with pytest.raises(SystemExit):
        data.validate_files(namedtuple("Args", args.keys())(*args.values()))


@pytest.mark.parametrize(
    ("file_type", "data_type"), [("stories", "story"), ("rules", "rule")]
)
def test_validate_files_form_not_found_invalid_domain(
    file_type: Text, data_type: Text, tmp_path: Path
):
    file_name = tmp_path / f"{file_type}.yml"
    file_name.write_text(
        f"""
        version: "{LATEST_TRAINING_DATA_FORMAT_VERSION}"
        {file_type}:
        - {data_type}: test path
          steps:
            - intent: request_restaurant
            - action: restaurant_form
            - active_loop: restaurant_form
        """
    )
    args = {
        "domain": "data/test_restaurantbot/domain.yml",
        "data": [file_name],
        "max_history": None,
        "config": "data/test_config/config_defaults.yml",
    }
    with pytest.raises(SystemExit):
        data.validate_files(namedtuple("Args", args.keys())(*args.values()))


@pytest.mark.parametrize(
    ("file_type", "data_type"), [("stories", "story"), ("rules", "rule")]
)
def test_validate_files_with_active_loop_null(
    file_type: Text, data_type: Text, tmp_path: Path
):
    domain_file = (
        "data/test_domains/minimal_domain_validate_files_with_active_loop_null.yml"
    )
    nlu_file = "data/test_nlu/test_nlu_validate_files_with_active_loop_null.yml"
    file_name = tmp_path / f"{file_type}.yml"
    file_name.write_text(
        f"""
        version: "{LATEST_TRAINING_DATA_FORMAT_VERSION}"
        {file_type}:
        - {data_type}: test path
          steps:
            - intent: request_restaurant
            - action: restaurant_form
            - active_loop: restaurant_form
            - active_loop: null
            - action: action_search_restaurants
        """
    )
    args = {
        "domain": domain_file,
        "data": [file_name, nlu_file],
        "max_history": None,
        "config": "data/test_config/config_unique_assistant_id.yml",
        "fail_on_warnings": False,
    }
    with pytest.warns() as warning_recorder:
        data.validate_files(namedtuple("Args", args.keys())(*args.values()))

    assert not [
        warning.message
        for warning in warning_recorder.list
        if not any(
            type(warning.message) == warning_type
            and re.search(warning_message, str(warning.message))
            for warning_type, warning_message in EXPECTED_WARNINGS
        )
    ]


def test_validate_files_form_slots_not_matching(tmp_path: Path):
    domain_file_name = tmp_path / "domain.yml"
    domain_file_name.write_text(
        f"""
        version: "{LATEST_TRAINING_DATA_FORMAT_VERSION}"
        forms:
          name_form:
            required_slots:
            - first_name
            - last_name
        slots:
             first_name:
                type: text
                mappings:
                - type: from_text
             last_nam:
                type: text
                mappings:
                - type: from_text
        """
    )
    args = {
        "domain": domain_file_name,
        "data": None,
        "max_history": None,
        "config": "data/test_config/config_defaults.yml",
    }
    with pytest.raises(SystemExit):
        data.validate_files(namedtuple("Args", args.keys())(*args.values()))


def test_validate_files_exit_early():
    with pytest.raises(SystemExit) as pytest_e:
        args = {
            "domain": "data/test_domains/duplicate_intents.yml",
            "data": None,
            "max_history": None,
            "config": "data/test_config/config_defaults.yml",
        }
        data.validate_files(namedtuple("Args", args.keys())(*args.values()))

    assert pytest_e.type == SystemExit
    assert pytest_e.value.code == 1


def test_validate_files_invalid_domain():
    args = {
        "domain": "data/test_domains/default_with_mapping.yml",
        "data": None,
        "max_history": None,
        "config": "data/test_config/config_defaults.yml",
    }

    with pytest.raises(SystemExit):
        data.validate_files(namedtuple("Args", args.keys())(*args.values()))
        with pytest.warns(UserWarning) as w:
            assert "Please migrate to RulePolicy." in str(w[0].message)


def test_validate_files_invalid_slot_mappings(tmp_path: Path):
    domain = tmp_path / "domain.yml"
    tested_slot = "duration"
    form_name = "booking_form"
    # form required_slots does not include the tested_slot
    domain.write_text(
        f"""
            version: "{LATEST_TRAINING_DATA_FORMAT_VERSION}"
            intents:
            - state_length_of_time
            entities:
            - city
            slots:
              {tested_slot}:
                type: text
                influence_conversation: false
                mappings:
                - type: from_text
                  intent: state_length_of_time
                  conditions:
                  - active_loop: {form_name}
              location:
                type: text
                mappings:
                - type: from_entity
                  entity: city
            forms:
              {form_name}:
                required_slots:
                - location
                """
    )
    args = {
        "domain": str(domain),
        "data": None,
        "max_history": None,
        "config": "data/test_config/config_defaults.yml",
        "fail_on_warnings": False,
    }
    with pytest.raises(SystemExit):
        data.validate_files(namedtuple("Args", args.keys())(*args.values()))


def test_validate_files_config_default_assistant_id():
    args = {
        "domain": "data/test_moodbot/domain.yml",
        "data": None,
        "max_history": None,
        "config": "data/test_config/config_defaults.yml",
        "fail_on_warnings": False,
    }
    msg = (
        f"The config file is missing a unique value for the "
        f"'{ASSISTANT_ID_KEY}' mandatory key. Please replace the default "
        f"placeholder value with a unique identifier."
    )
    with pytest.warns(UserWarning, match=msg):
        data.validate_files(namedtuple("Args", args.keys())(*args.values()))


def test_validate_files_config_missing_assistant_id():
    args = {
        "domain": "data/test_moodbot/domain.yml",
        "data": None,
        "max_history": None,
        "config": "data/test_config/config_no_assistant_id.yml",
        "fail_on_warnings": False,
    }
    msg = f"The config file is missing the '{ASSISTANT_ID_KEY}' mandatory key."
    with pytest.warns(UserWarning, match=msg):
        data.validate_files(namedtuple("Args", args.keys())(*args.values()))


def test_data_split_stories(run_in_simple_project: Callable[..., RunResult]):
    stories_yml = (
        "stories:\n"
        "- story: story 1\n"
        "  steps:\n"
        "  - intent: intent_a\n"
        "  - action: utter_a\n"
        "- story: story 2\n"
        "  steps:\n"
        "  - intent: intent_a\n"
        "  - action: utter_a\n"
    )

    Path("data/stories.yml").write_text(stories_yml)
    run_in_simple_project(
        "data", "split", "stories", "--random-seed", "123", "--training-fraction", "0.5"
    )

    folder = Path("train_test_split")
    assert folder.exists()

    train_file = folder / "train_stories.yml"
    assert train_file.exists()
    test_file = folder / "test_stories.yml"
    assert test_file.exists()

    train_data = rasa.shared.utils.io.read_yaml_file(train_file)
    assert len(train_data.get("stories", [])) == 1
    assert train_data["stories"][0].get("story") == "story 1"
    test_data = rasa.shared.utils.io.read_yaml_file(test_file)
    assert len(test_data.get("stories", [])) == 1
    assert test_data["stories"][0].get("story") == "story 2"
