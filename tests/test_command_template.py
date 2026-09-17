"""Command-template expansion guards.

Regression coverage for a real portability bug: the UVR/SVC runners used to
split the configured command on whitespace *before* substituting placeholders,
so any runtime, model, or song path containing a space (``C:\\Program Files``,
``D:\\My Music\\song.mp3``) was torn into several argv entries and the child
process failed with a confusing argument error.

The template is now tokenised first and substituted afterwards; these tests pin
that contract down for every consumer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aivoice_studio.modules.svc.svc_runner import SVCService
from aivoice_studio.modules.uvr.config import UVRConfig
from aivoice_studio.modules.uvr.separator import UVRService
from aivoice_studio.utils.process import split_command_template


# --- the shared helper -------------------------------------------------------


def test_plain_template_is_split_on_whitespace() -> None:
    assert split_command_template("python run.py --flag value") == [
        "python",
        "run.py",
        "--flag",
        "value",
    ]


def test_substituted_value_may_contain_spaces() -> None:
    argv = split_command_template(
        "{python} run.py --input {input}",
        python="C:/Program Files/Python/python.exe",
        input="C:/My Music/my song.mp3",
    )
    assert argv == [
        "C:/Program Files/Python/python.exe",
        "run.py",
        "--input",
        "C:/My Music/my song.mp3",
    ]


def test_unquoted_placeholder_with_spaces_stays_one_argument() -> None:
    """The old implementation produced 3 arguments here."""
    argv = split_command_template("--out {output}", output="D:/a b c/out")
    assert argv == ["--out", "D:/a b c/out"]


@pytest.mark.parametrize("quote", ['"', "'"])
def test_quotes_around_a_token_are_honoured(quote: str) -> None:
    argv = split_command_template(f"--input {quote}{{input}}{quote}", input="C:/a b.mp3")
    assert argv == ["--input", "C:/a b.mp3"]


def test_placeholder_expanding_to_empty_string_is_kept() -> None:
    """An optional value compiles to an empty argv entry, not a dropped flag."""
    assert split_command_template("--accompaniment {value}", value="") == [
        "--accompaniment",
        "",
    ]


def test_quoted_empty_token_is_dropped_like_str_split() -> None:
    """Matches the previous ``template.split()`` behaviour for literal ``""``."""
    assert split_command_template('--accompaniment ""') == ["--accompaniment"]


def test_backslashes_are_not_treated_as_escapes() -> None:
    argv = split_command_template(r"{python} -m x", python=r"tools\so-vits-svc\workenv\python.exe")
    assert argv == [r"tools\so-vits-svc\workenv\python.exe", "-m", "x"]


def test_unknown_placeholder_fails_loudly() -> None:
    with pytest.raises(KeyError):
        split_command_template("{missing} arg")


def test_empty_template_yields_no_arguments() -> None:
    assert split_command_template("") == []
    assert split_command_template("   ") == []


# --- consumers ---------------------------------------------------------------


def test_uvr_service_builds_a_single_argument_per_path(tmp_path: Path) -> None:
    config = UVRConfig(
        command=(
            "{python} scripts/uvr_directml.py {input} --output_dir {output_dir} "
            "--model_filename {model_name} --model_file_dir models/uvr"
        ),
        model_name="UVR_MNEXNET_Main.onnx",
        mock_mode=True,
    )
    service = UVRService(config)
    input_path = tmp_path / "My Music" / "a song.mp3"
    output_dir = tmp_path / "sep out"

    argv = service._build_command(input_path, output_dir)

    assert str(input_path) in argv
    assert str(output_dir) in argv
    assert "a song.mp3" in str(input_path)
    # Placeholders were fully expanded; nothing was split on the embedded space.
    assert not any("{input}" in token or "{output_dir}" in token for token in argv)
    assert argv.count(str(input_path)) == 1


def test_svc_service_split_command_keeps_spaced_runtime_path() -> None:
    argv = SVCService._split_command(
        "{python} {script} -m {model_path} -c {config_path} -n {input_name}",
        python=r"C:\Program Files\svc\python.exe",
        script="inference_main.py",
        model_path="G_10000.pth",
        config_path="config.json",
        input_name="a song.wav",
    )
    assert argv == [
        r"C:\Program Files\svc\python.exe",
        "inference_main.py",
        "-m",
        "G_10000.pth",
        "-c",
        "config.json",
        "-n",
        "a song.wav",
    ]


def test_yaml_placeholder_braces_survive_a_round_trip() -> None:
    """config/uvr.yaml stores the same template shape that the runner expands."""
    yaml_line = (
        "{python} scripts/uvr_directml.py {input} --output_dir {output_dir} "
        "--model_filename {model_name} --model_file_dir models/uvr"
    )
    argv = split_command_template(
        yaml_line,
        python="python.exe",
        input="in.mp3",
        output_dir="out",
        model_name="m.onnx",
    )
    assert argv == [
        "python.exe",
        "scripts/uvr_directml.py",
        "in.mp3",
        "--output_dir",
        "out",
        "--model_filename",
        "m.onnx",
        "--model_file_dir",
        "models/uvr",
    ]
