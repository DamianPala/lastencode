"""Public CLI contracts and preset behavior, without network or media."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from lastencode import __version__
from lastencode.__main__ import main

TARGETS = ["portable", "desktop"]
FIELDS = {
    "encoder",
    "quality_crf",
    "speed_preset",
    "extra_encoder_params",
    "deblocking",
    "bit_depth",
    "scale_short_side",
    "audio_codec",
    "audio_bitrate_bps",
    "audio_channel_rule",
    "audio_dual_mono_bitrate_bps",
    "keyframe_interval_seconds",
    "copy_video_below_bps",
    "max_frame_rate",
    "drop_repeated_frames",
}
SVT_TALK = (
    "tune=1:enable-variance-boost=1:ac-bias=1.0:tf-strength=1:sharpness=1:"
    "enable-qm=1:qm-min=2:scm=1"
)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "lastencode", *args],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        check=False,
    )


def document(*args: str) -> dict[str, Any]:
    result = cli(*args)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.endswith("\n")
    return json.loads(result.stdout)


def categories(*args: str) -> dict[str, Any]:
    return {item["name"]: item for item in document("presets", *args)["categories"]}


def write_presets(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "presets.toml"
    path.write_text(content)
    return path


def assert_invalid(result: subprocess.CompletedProcess[str], problem: str) -> None:
    assert result.returncode == 2
    assert result.stdout == ""
    error = json.loads(result.stderr.splitlines()[-1])
    assert set(error) == {"error"}
    assert error["error"]["kind"] == "invalid_input"
    assert problem in error["error"]["message"]
    assert "Traceback" not in result.stderr


def test_schema_index_and_both_details() -> None:
    index = document("schema", "--json")
    assert index["conformance"] == {
        "name": "cli-design-standard",
        "standard": "0.2.0-draft.12",
        "extensions": [],
    }
    assert index["schema_version"] == "1"
    assert index["tool_version"] == __version__
    assert set(index["exit_codes"]) == {"0", "1", "2", "3"}
    assert "missing" in index["exit_codes"]["3"]
    # D6a explicitly excludes introspection from the command index.
    assert [command["name"] for command in index["commands"]] == [
        "bench",
        "convert",
        "presets",
    ]
    assert index["format_defaults"] == {"tty": "text", "non_tty": "json"}
    for name in ["presets"]:
        detail = document("schema", name)
        assert detail["name"] == name
        assert detail["effects"] == "read_only"
        assert detail["confirm"] is False
        assert detail["interactive"] is False
        assert "output" in detail
        assert all(flag["name"] != "json" for flag in detail["flags"])


def test_schema_needs_no_configuration(tmp_path: Path) -> None:
    path = write_presets(tmp_path, "broken [ TOML")
    assert document("--presets", str(path), "schema")["schema_version"] == "1"
    assert document("schema", "--presets", str(path), "presets")["name"] == "presets"
    assert document("schema", "--presets", str(tmp_path / "missing"))["schema_version"] == "1"


@pytest.mark.parametrize(
    "args",
    [
        (),
        ("schema", "nope"),
        ("convert",),
        ("bench",),
        ("presets", "--wat"),
        ("presets", "--js"),
        ("presets", "--", "--json"),
    ],
)
def test_invalid_cli(args: tuple[str, ...]) -> None:
    assert_invalid(cli(*args), "")


def test_format_and_global_flag_positions() -> None:
    assert document("--json", "presets") == document("presets", "--json")
    assert document("presets") == document("presets", "--format", "json")
    assert_invalid(cli("--json", "presets", "--format", "text"), "mutually exclusive")
    assert_invalid(cli("presets", "--format", "json", "--json"), "mutually exclusive")
    assert_invalid(cli("presets", "--format", "yaml"), "json")


def test_version_and_help() -> None:
    assert cli("--version").stdout == f"{__version__}\n"
    for args in [("--help",), ("presets", "--help"), ("schema", "--help")]:
        result = cli(*args)
        assert result.returncode == 0
        assert "usage:" in result.stdout
        assert "--json" in result.stdout
    assert "lastencode schema" in cli("--help").stdout


def test_r1_all_effective_settings_and_provenance() -> None:
    data = document("presets", "--json")
    assert data["playback_targets"] == TARGETS
    assert len(data["categories"]) == 5
    for category in data["categories"]:
        assert category["description"] and "\n" not in category["description"]
        assert category["base"] is None
        assert category["location"]["value"] == "keep"
        for target in TARGETS:
            assert set(category[target]) == FIELDS
            for setting in category[target].values():
                assert set(setting) == {"value", "origin"}
                assert setting["origin"] == "builtin"


@pytest.mark.parametrize(
    "name,desktop_crf,opus,keyframes,scale,threshold",
    [
        ("apartment-tour", 28, 48000, 2, 0, 1500000),
        ("dance-lesson", 28, 64000, 2, 720, 1000000),
        ("webinar", 50, 48000, 5, 0, 300000),
        ("call", 45, 48000, 5, 360, 300000),
        ("holiday", 26, 64000, 2, 0, 1500000),
    ],
)
def test_r9_table(
    *, name: str, desktop_crf: int, opus: int, keyframes: int, scale: int, threshold: int
) -> None:
    category = categories()[name]
    assert "starting_point" not in json.dumps(category)
    for target in TARGETS:
        values = {key: setting["value"] for key, setting in category[target].items()}
        talk = name in {"webinar", "call"}
        desktop = target == "desktop" and talk
        assert values["encoder"] == ("libsvtav1" if desktop else "libx265")
        assert values["quality_crf"] == (
            desktop_crf if desktop else 26 if name == "holiday" else 28
        )
        assert values["speed_preset"] == ("4" if desktop else "slow")
        assert values["bit_depth"] == 10
        assert values["audio_codec"] == "opus"
        assert values["audio_bitrate_bps"] == opus
        conditional = talk
        assert values["audio_channel_rule"] == (
            "dual-mono-to-mono-otherwise-stereo" if conditional else "preserve"
        )
        assert values["audio_dual_mono_bitrate_bps"] == (
            24000 if conditional else values["audio_bitrate_bps"]
        )
        assert values["keyframe_interval_seconds"] == keyframes
        assert values["scale_short_side"] == scale
        assert values["copy_video_below_bps"] == ("never" if talk and desktop else threshold)
        assert values["drop_repeated_frames"] is (talk and desktop)
        assert values["max_frame_rate"] == (25 if talk else "native")
        assert values["deblocking"] == "default"
        params = ""
        if talk and desktop:
            params = SVT_TALK
        if name == "dance-lesson" and not desktop:
            params = "aq-mode=3:aq-strength=1.1"
        assert values["extra_encoder_params"] == params


def test_user_override_and_inheritance(tmp_path: Path) -> None:
    path = write_presets(
        tmp_path,
        """
[categories.dance-lesson.portable]
quality_crf = 25
deblocking = "-1:-1"
[categories.webinar.portable]
max_frame_rate = 30
[categories.apartment-tour.desktop]
max_frame_rate = "native"
[categories.private-dance]
base = "dance-lesson"
location = "strip"
description = "Lessons for sharing."
[categories.second-generation]
base = "private-dance"
[categories.private-dance.desktop]
copy_video_below_bps = "never"
""",
    )
    data = categories("--presets", str(path))
    expected = {"value": 25, "origin": str(path)}
    for name in ["dance-lesson", "private-dance", "second-generation"]:
        assert data[name]["portable"]["quality_crf"] == expected
        assert data[name]["portable"]["scale_short_side"]["origin"] == "builtin"
    assert data["private-dance"]["base"] == "dance-lesson"
    assert data["private-dance"]["location"] == {
        "value": "strip",
        "origin": str(path),
    }
    assert data["second-generation"]["description"] == "Lessons for sharing."
    assert data["second-generation"]["desktop"]["copy_video_below_bps"]["value"] == "never"
    assert data["webinar"]["portable"]["max_frame_rate"]["value"] == 30
    assert data["webinar"]["portable"]["max_frame_rate"]["origin"] == str(path)
    assert data["apartment-tour"]["desktop"]["max_frame_rate"]["value"] == "native"


@pytest.mark.parametrize(
    "content,problem",
    [
        ("unknown = 1", "unknown"),
        ("[categories.dance-lesson]\nwat = 2", "wat"),
        ("[categories.dance-lesson.phone]", "phone"),
        ("[categories.dance-lesson.portable]\nwat = 2", "wat"),
        ('[categories.dance-lesson.portable]\nquality_crf = "28"', "quality_crf"),
        ("[categories.dance-lesson.portable]\nquality_crf = true", "quality_crf"),
        ("[categories.dance-lesson.portable]\nquality_crf = 28.0", "quality_crf"),
        ("[categories.dance-lesson.portable]\ndrop_repeated_frames = 1", "drop_repeated_frames"),
        ("[categories.dance-lesson.portable]\nbit_depth = 12", "valid values"),
        ('[categories.dance-lesson.portable]\nencoder = "gpu"', "valid values"),
        ("[categories.dance-lesson.portable]\naudio_bitrate_bps = -1", "audio_bitrate_bps"),
        ('[categories.dance-lesson.portable]\nmax_frame_rate = "30"', "max_frame_rate"),
        ("[categories.dance-lesson.portable]\nmax_frame_rate = 0", "max_frame_rate"),
        ("[categories.dance-lesson.portable]\nmax_frame_rate = true", "max_frame_rate"),
        ('[categories.dance-lesson]\nlocation = "public"', "keep, strip"),
        ('[categories.new]\nbase = "missing"', "unknown base"),
        ("[categories.new]", "requires"),
        ("[categories.new]\nbase = 3", "base"),
        ('[categories.new]\nbase = "other"\n[categories.other]\nbase = "new"', "cyclic"),
        ('[categories."Bad Name"]\nbase = "call"', "invalid category name"),
        ("[categories.call]\nportable = 4", "expected a TOML table"),
        ("[categories.call]\ndescription = 4", "description"),
        ("categories = []", "expected a TOML table"),
        ("broken [ TOML", "cannot read"),
    ],
)
def test_invalid_preset_files(tmp_path: Path, content: str, problem: str) -> None:
    path = write_presets(tmp_path, content)
    assert_invalid(cli("presets", "--presets", str(path), "--json"), problem)


def test_missing_explicit_and_directory_are_usage_errors(tmp_path: Path) -> None:
    assert_invalid(cli("presets", "--presets", str(tmp_path / "missing")), "does not exist")
    assert_invalid(cli("presets", "--presets", str(tmp_path)), "cannot read")


def test_precedence_over_xdg(tmp_path: Path) -> None:
    config = Path(os.environ["XDG_CONFIG_HOME"]) / "lastencode" / "presets.toml"
    config.parent.mkdir(parents=True)
    config.write_text("[categories.call.portable]\nquality_crf = 22")
    assert categories()["call"]["portable"]["quality_crf"]["origin"] == str(config)
    assert categories()["call"]["portable"]["quality_crf"]["value"] == 22
    explicit = write_presets(tmp_path, "[categories.call.portable]\nquality_crf = 24")
    data = document("--presets", str(explicit), "presets")
    call = next(category for category in data["categories"] if category["name"] == "call")
    assert call["portable"]["quality_crf"]["value"] == 24
    config.write_text("invalid TOML = [")
    assert categories("--presets", str(explicit))["call"]["portable"]["quality_crf"]["value"] == 24


def test_input_bounds(tmp_path: Path) -> None:
    path = write_presets(tmp_path, "#" * (1_048_576 + 1))
    assert_invalid(cli("presets", "--presets", str(path)), "exceeds")
    path.write_text("\n".join(f'[categories.c{i}]\nbase = "call"' for i in range(252)))
    assert_invalid(cli("presets", "--presets", str(path)), "256 categories")


def test_human_output_and_untrusted_controls(tmp_path: Path) -> None:
    result = cli("presets", "--format", "text")
    assert result.returncode == 0
    assert "dance-lesson" in result.stdout
    assert "portable" in result.stdout
    assert "starting point" not in result.stdout
    assert "*" not in result.stdout
    assert "[builtin]" in result.stdout
    path = write_presets(tmp_path, '[categories.call]\ndescription = "Escape \\u001b[2J"')
    result = cli("presets", "--presets", str(path), "--format", "text")
    assert result.returncode == 0
    assert "\x1b" not in result.stdout
    assert r"\u001b[2J" in result.stdout


def validate_schema(value: Any, schema: dict[str, Any]) -> None:
    if not schema:
        return
    if "oneOf" in schema:
        validate_one_of(value, schema["oneOf"])
        return
    kind = schema["type"]
    if value is None:
        assert "null" in kind
        return
    if isinstance(kind, list):
        kind = kind[0]
    types = {
        "object": (dict,),
        "array": (list,),
        "string": (str,),
        "integer": (int,),
        "boolean": (bool,),
        "number": (int, float),
    }
    assert type(value) in types[kind]
    if "enum" in schema:
        assert value in schema["enum"]
    if kind == "object":
        validate_object(value, schema)
    if kind == "array":
        validate_array(value, schema["items"])


def validate_object(value: dict[str, Any], schema: dict[str, Any]) -> None:
    assert set(schema["required"]) <= value.keys()
    assert value.keys() <= schema["properties"].keys()
    for key, item in value.items():
        validate_schema(item, schema["properties"][key])


def validate_one_of(value: Any, branches: list[dict[str, Any]]) -> None:
    matches = [
        value == branch["const"]
        if "const" in branch
        else type(value) is int and value >= branch["minimum"]
        for branch in branches
    ]
    assert sum(matches) == 1


def validate_array(value: list[Any], schema: dict[str, Any]) -> None:
    for item in value:
        validate_schema(item, schema)


def test_presets_result_matches_published_schema(tmp_path: Path) -> None:
    schema = document("schema", "presets")["output"]
    validate_schema(document("presets"), schema)
    path = write_presets(tmp_path, '[categories.custom]\nbase = "webinar"\nlocation = "strip"')
    validate_schema(document("presets", "--presets", str(path)), schema)


@pytest.mark.parametrize(
    "args",
    [
        ("presets", "--json", "--json"),
        ("--json", "presets", "--json"),
        ("presets", "--format=text", "--format=json"),
    ],
)
def test_repeated_format_flags_are_invalid(args: tuple[str, ...]) -> None:
    assert_invalid(cli(*args), "mutually exclusive")


def test_default_terminal_format(monkeypatch: pytest.MonkeyPatch) -> None:
    class Terminal(io.StringIO):
        def isatty(self) -> bool:
            return True

    output = Terminal()
    monkeypatch.setattr(sys, "stdout", output)
    assert main(["presets"]) == 0
    assert output.getvalue().startswith("Presets (provenance")
    output.seek(0)
    output.truncate()
    assert main(["schema"]) == 0
    assert json.loads(output.getvalue())["schema_version"] == "1"


def test_pipeline_closure_is_quiet() -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "lastencode", "presets", "--json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None and process.stderr is not None
    process.stdout.close()
    assert process.wait(timeout=10) == 0
    assert process.stderr.read() == ""
    process.stderr.close()


def test_invalid_utf8(tmp_path: Path) -> None:
    path = tmp_path / "presets.toml"
    path.write_bytes(b"\xff")
    assert_invalid(cli("presets", "--presets", str(path)), "cannot read")


def test_r9b_rejects_removed_target(tmp_path: Path) -> None:
    path = write_presets(tmp_path, "[categories.webinar.compat]\nquality_crf = 28")
    result = cli("presets", "--presets", str(path), "--json")
    assert_invalid(result, "compat")
    assert "portable" in result.stderr and "desktop" in result.stderr


@pytest.mark.parametrize("args", [("--bogus",), ("presets", "--bogus")])
def test_r33_unknown_option_names_flag(args: tuple[str, ...]) -> None:
    assert_invalid(cli(*args), "--bogus")


def test_r2_missing_category_names_recovery_values() -> None:
    result = cli("convert", "--dry-run")
    assert_invalid(result, "missing --category")
    assert "apartment-tour" in result.stderr
    assert "None" not in result.stderr
