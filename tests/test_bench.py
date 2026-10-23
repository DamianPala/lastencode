"""Benchmark command and scoring behavior on generated test clips."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from typing import cast

import pytest

import lastencode.commands.bench as bench
from fixture_builders import _run
from lastencode.check_media import scan
from lastencode.errors import InvalidInput, MissingTool
from lastencode.paths import Source
from lastencode.presets import builtin_categories, load_categories
from lastencode.probe import probe
from test_cli import document
from test_picture_facts import media

pytestmark = pytest.mark.linux_only


def run_cli_with_path(path: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "lastencode", *args],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": path},
        check=False,
    )


def test_bench_schema_lists_flags_and_output() -> None:
    detail = document("schema", "bench")
    assert detail["name"] == "bench"
    assert {flag["name"] for flag in detail["flags"]} >= {
        "category",
        "output-dir",
        "target",
        "quality-settings",
        "excerpt-seconds",
        "excerpts",
        "include-25-fps",
        "dry-run",
    }
    assert "rows" in detail["output"]["properties"]
    assert "bench.csv" in detail["output_description"]


def test_default_variants_follow_the_target_preset(fast_presets: Path) -> None:
    category = next(
        category
        for category in load_categories(str(fast_presets))
        if category.name == "apartment-tour"
    )
    variants = bench.make_variants(category, ["portable"], None, True)
    assert [(variant.quality_crf, variant.frame_rate_change) for variant in variants] == [
        (26, "native"),
        (26, "25 fps"),
        (28, "native"),
        (28, "25 fps"),
        (30, "native"),
        (30, "25 fps"),
    ]
    assert {variant.target for variant in variants} == {"portable"}
    assert all(variant.settings["speed_preset"] == "ultrafast" for variant in variants)


def test_excerpt_spread_and_playback_frame_mapping() -> None:
    assert bench.excerpt_starts(20, 5, 3) == [0, 7.5, 15]
    assert bench.matching_frame_times([Fraction(0), Fraction(1)], [Fraction(1, 1000), Fraction(1)])
    assert not bench.matching_frame_times([Fraction(0)], [Fraction(1, 100)])
    mapping = bench.held_frame_indices(
        [Fraction(0), Fraction(1), Fraction(3)],
        [Fraction(0), Fraction(1, 2), Fraction(1), Fraction(2), Fraction(3)],
    )
    assert mapping == [0, 0, 1, 1, 2]
    assert bench.held_frame_indices(
        [Fraction(0), Fraction(1001, 1000)], [Fraction(0), Fraction(1)]
    ) == [0, 1]
    with pytest.raises(ValueError, match="starts after"):
        bench.held_frame_indices([Fraction(1)], [Fraction(0)])


@pytest.mark.parametrize(
    ("error_type", "message"),
    [(MissingTool, "ffprobe failed"), (InvalidInput, "no video stream")],
)
def test_variant_probe_errors_make_an_invalid_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
    message: str,
) -> None:
    source_path = tmp_path / "source.mkv"
    source = Source(source_path, tmp_path, tmp_path / "output", tmp_path / "no-gain")
    info = cast(
        dict[str, object],
        {
            "streams": [
                {
                    "codec_type": "video",
                    "index": 0,
                    "width": 16,
                    "height": 16,
                    "pix_fmt": "yuv420p",
                    "color_range": "tv",
                }
            ]
        },
    )
    plan = bench.ExcerptPlan(source, 1, info, 10, 100, 1, 0, 5, tmp_path / "excerpt.mkv")
    variant = bench.Variant("portable", 28, "native", {"drop_repeated_frames": False})
    output = tmp_path / "output"
    (output / "variants").mkdir(parents=True)
    work = tmp_path / "work"
    work.mkdir()
    original_probe = bench.probe

    def fake_probe(path: Path, *, packet_times: bool = False) -> dict[str, object]:
        if path.name.endswith(".mp4"):
            raise error_type(message)
        return original_probe(path) if path.exists() else info

    def fake_encode(
        _reference: Path,
        _reference_info: dict[str, object],
        _variant: bench.Variant,
        path: Path,
        _frame_rate_cap: int | None = None,
    ) -> tuple[None, float]:
        path.write_bytes(b"encoded")
        return None, 0.01

    monkeypatch.setattr(bench, "probe", fake_probe)
    monkeypatch.setattr(bench, "encode_variant", fake_encode)
    row = bench.process_variant(plan, variant, 1, plan.path, output, work, None)
    assert row["valid"] is False
    assert row["reason"] == message


@pytest.mark.needs_media
def test_dry_run_creates_no_output(
    phone_clip: Path,
    fast_presets: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bench, "check_bench_tools", lambda _variants: None)
    monkeypatch.setattr(bench, "check_variant_encoders", lambda _variants: None)
    output = tmp_path / "bench"
    result = bench.run(
        argparse.Namespace(
            sources=[str(phone_clip)],
            category="apartment-tour",
            output_dir=str(output),
            target=None,
            quality_settings=[26, 28, 30],
            excerpt_seconds=5,
            excerpts=3,
            include_25_fps=True,
            dry_run=True,
            force=False,
            presets=str(fast_presets),
        )
    )
    assert result["dry_run"] is True
    assert result["variant_count"] == 6
    assert result["encode_count"] == 18
    assert int(str(result["space_estimate_bytes"])) > 0
    assert not output.exists()


@pytest.mark.needs_media
@pytest.mark.posix_only
def test_r30_old_ffmpeg_without_libvmaf_exits_3(tmp_path: Path, fast_presets: Path) -> None:
    stub = tmp_path / "bin" / "ffmpeg"
    stub.parent.mkdir()
    real = shutil.which("ffmpeg")
    stub.write_text(
        "#!/usr/bin/env python3\nimport os, sys\n"
        "if '-version' in sys.argv: print('ffmpeg version 9.0'); sys.exit(0)\n"
        "if '-filters' in sys.argv: print('no filters'); sys.exit(0)\n"
        f"os.execv({real!r}, [{real!r}] + sys.argv[1:])\n"
    )
    stub.chmod(0o755)
    source = tmp_path / "input" / "clip.mp4"
    source.parent.mkdir()
    source.write_bytes(b"synthetic path for preflight")
    output = tmp_path / "output"
    path = os.pathsep.join([str(stub.parent), os.environ.get("PATH", "")])
    result = run_cli_with_path(
        path,
        "bench",
        str(source),
        "--category",
        "apartment-tour",
        "--output-dir",
        str(output),
        "--presets",
        str(fast_presets),
        "--dry-run",
    )
    assert result.returncode == 3, result.stderr
    assert "libvmaf" in result.stderr
    assert not output.exists()


@pytest.mark.slow
@pytest.mark.needs_media
def test_identical_lossless_variant_scores_near_100(tmp_path: Path) -> None:
    reference = tmp_path / "reference.mkv"
    variant = tmp_path / "variant.mkv"
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=1280x720:r=25:d=5",
            "-c:v",
            "ffv1",
            "-g",
            "1",
            str(reference),
        ]
    )
    shutil.copyfile(reference, variant)
    info = probe(reference)
    work = tmp_path / "score"
    work.mkdir()
    desktop_mean, desktop_p5, phone_mean, phone_p5 = bench.score_vmaf(
        variant, info, reference, info, work, "identical"
    )
    assert desktop_mean >= 99.5 and desktop_p5 >= 99.5
    assert phone_mean >= 99.5 and phone_p5 >= 99.5


def frame_luma_hashes(
    path: Path, start: float | None = None, duration: float | None = None
) -> list[str]:
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin"]
    if start is not None:
        command.extend(["-ss", f"{start:.6f}"])
    command.extend(["-i", str(path)])
    if duration is not None:
        command.extend(["-t", f"{duration:.6f}"])
    command.extend(
        [
            "-map",
            "0:v:0",
            "-vf",
            "extractplanes=y",
            "-fps_mode",
            "passthrough",
            "-f",
            "framemd5",
            "-",
        ]
    )
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    return [
        line.rsplit(",", 1)[-1].strip()
        for line in result.stdout.splitlines()
        if line and not line.startswith("#")
    ]


@pytest.mark.slow
@pytest.mark.needs_media
def test_full_range_phone_excerpt_preserves_luma_and_25fps_range(
    phone_clip: Path, tmp_path: Path
) -> None:
    source = Source(phone_clip, phone_clip.parent, tmp_path / "output", tmp_path / "no-gain")
    output = tmp_path / "output"
    (output / "excerpts").mkdir(parents=True)
    plan = bench.plan_excerpts([source], output, 1, 5)[0]
    assert not plan.source_info["first_frame"]
    assert bench.ffmpeg_range(bench.video_stream(plan.source_info)) == "limited"
    assert bench.cut_excerpt(plan) is None
    assert probe(plan.path)["color_range"] == "pc"
    source_hashes = frame_luma_hashes(phone_clip, plan.start_seconds, plan.duration_seconds)
    excerpt_hashes = frame_luma_hashes(plan.path)
    assert excerpt_hashes == source_hashes

    transformed = output / "excerpts" / "phone-25fps.mkv"
    assert bench.make_25fps_reference(plan.path, transformed) is None
    assert probe(transformed)["color_range"] == "pc"


@pytest.mark.slow
@pytest.mark.needs_media
@pytest.mark.parametrize("explicit_native", [False, True])
def test_r27_bench_webinar_default_cap_and_explicit_native(
    sixty_fps_clip: Path, fast_presets: Path, tmp_path: Path, explicit_native: bool
) -> None:
    path = os.environ["PATH"]
    output = tmp_path / "bench-webinar-cap"
    result = run_cli_with_path(
        path,
        "bench",
        str(sixty_fps_clip),
        "--category",
        "webinar",
        "--quality-settings",
        "28",
        "--excerpt-seconds",
        "5",
        "--excerpts",
        "1",
        "--output-dir",
        str(output),
        "--presets",
        str(fast_presets),
        "--json",
        *(["--include-25-fps"] if explicit_native else []),
    )
    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)["rows"]
    assert len(rows) == (2 if explicit_native else 1)
    expected = {"native": 60, "25 fps": 25} if explicit_native else {"preset cap (25 fps)": 25}
    assert {row["frame_rate_change"] for row in rows} == set(expected)
    for row in rows:
        assert row["valid"] is True, row["reason"]
        info = probe(Path(row["variant_path"]), packet_times=True)
        assert round(float(bench.frame_rate(info))) == expected[row["frame_rate_change"]]


@pytest.mark.slow
@pytest.mark.needs_media
def test_still_clip_dropped_frames_expand_and_score(
    still_clip: Path, fast_presets: Path, tmp_path: Path
) -> None:
    path = os.environ["PATH"]
    output = tmp_path / "bench"
    result = run_cli_with_path(
        path,
        "bench",
        str(still_clip),
        "--category",
        "webinar",
        "--target",
        "desktop",
        "--quality-settings",
        "50",
        "--excerpt-seconds",
        "8",
        "--excerpts",
        "2",
        "--output-dir",
        str(output),
        "--presets",
        str(fast_presets),
        "--json",
    )
    assert result.returncode == 0, result.stderr
    document_data = json.loads(result.stdout)
    for row in document_data["rows"]:
        assert row["valid"] is True, row["reason"]
        assert row["dropped_frame_share"] > 0
        assert row["vmaf_desktop_mean"] is not None
        assert Path(row["side_by_side_path"]).is_file()


@pytest.mark.slow
@pytest.mark.needs_media
def test_r28_r30_acceptance_phone_bench_dry_run_estimate_and_outputs(
    phone_clip: Path, fast_presets: Path, tmp_path: Path
) -> None:
    path = os.environ["PATH"]
    output = tmp_path / "bench"
    options = [
        str(phone_clip),
        "--category",
        "apartment-tour",
        "--quality-settings",
        "26",
        "--quality-settings",
        "28",
        "--quality-settings",
        "30",
        "--include-25-fps",
        "--excerpt-seconds",
        "5",
        "--excerpts",
        "3",
        "--output-dir",
        str(output),
        "--presets",
        str(fast_presets),
        "--json",
    ]
    dry_run = run_cli_with_path(path, "bench", *options, "--dry-run")
    assert dry_run.returncode == 0, dry_run.stderr
    estimate = json.loads(dry_run.stdout)["space_estimate_bytes"]
    assert not output.exists()
    result = run_cli_with_path(path, "bench", *options)
    assert result.returncode == 0, result.stderr
    document_data = json.loads(result.stdout)
    rows = document_data["rows"]
    assert len(rows) == 18
    assert all(row["valid"] for row in rows)
    for row in rows:
        for metric in (
            "vmaf_desktop_mean",
            "vmaf_desktop_p5",
            "vmaf_phone_mean",
            "vmaf_phone_p5",
            "xpsnr_y",
            "encode_time_realtime_multiple",
        ):
            assert isinstance(row[metric], int | float), (metric, row)
        assert 20 < row["xpsnr_y"] < 80, row
        assert Path(row["side_by_side_path"]).is_file()
    with (output / "bench.csv").open(newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    assert len(csv_rows) == len(rows)
    assert not any("ssimulacra" in key for key in csv_rows[0])
    for csv_row in csv_rows:
        assert float(csv_row["encode_time_realtime_multiple"]) == pytest.approx(
            float(csv_row["encode_time_seconds"]) / float(csv_row["excerpt_seconds"]), abs=1e-6
        )
    files = [path for path in output.rglob("*") if path.is_file()]
    assert len([path for path in files if path.parent.name == "side-by-side"]) == 18
    assert estimate >= sum(path.stat().st_size for path in files)
    assert probe(Path(rows[0]["side_by_side_path"]))["color_range"] == "pc"


def test_R27_explicit_native_bypasses_cap_default_keeps_it() -> None:
    category = builtin_categories()["webinar"]
    excerpt = media([i / 60 for i in range(120)], 1 / 60)
    native, capped = bench.make_variants(category, ["portable"], [28], True)
    assert bench.variant_frame_rate_cap(native, excerpt) is None
    assert bench.variant_frame_rate_cap(capped, excerpt) == 25
    default = bench.make_variants(category, ["portable"], [28], False)[0]
    assert bench.variant_frame_rate_cap(default, excerpt) == 25


@pytest.mark.needs_media
def test_R27_native_and_25_encodes_keep_distinct_rates(tmp_path: Path, fast_presets: Path) -> None:
    source = tmp_path / "sixty.mp4"
    _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=160x120:r=60:d=2",
            "-c:v",
            "libx264",
            str(source),
        ]
    )
    category = next(c for c in load_categories(str(fast_presets)) if c.name == "webinar")
    variants = bench.make_variants(category, ["portable"], [28], True)
    info = probe(source)
    for variant, expected in zip(variants, (60, 25), strict=True):
        output = tmp_path / f"{expected}.mp4"
        cap = bench.variant_frame_rate_cap(variant, scan(source))
        error, _ = bench.encode_variant(source, info, variant, output, cap)
        assert error is None
        actual = scan(output).times
        assert round((len(actual) - 1) / (actual[-1] - actual[0])) == expected


@pytest.mark.needs_media
def test_r27b_existing_csv_requires_force_before_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phone_clip: Path
) -> None:
    output = tmp_path / "bench"
    output.mkdir()
    csv_path = output / "bench.csv"
    csv_path.write_text("previous benchmark\n")
    (output / "keep.txt").write_text("untouched")
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in output.iterdir()}
    result = run_cli_with_path(
        os.environ["PATH"],
        "bench",
        str(phone_clip),
        "--category",
        "webinar",
        "--output-dir",
        str(output),
        "--json",
    )
    assert result.returncode == 1, result.stderr
    assert "--force" in result.stderr
    assert {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in output.iterdir()} == before

    source = tmp_path / "input" / "source.mp4"
    source.parent.mkdir()
    source.write_bytes(b"synthetic source path")
    monkeypatch.setattr(bench, "check_bench_tools", lambda _: None)
    monkeypatch.setattr(bench, "check_variant_encoders", lambda _: None)
    monkeypatch.setattr(bench, "plan_excerpts", lambda *_: [])
    monkeypatch.setattr(bench, "execute_benchmark", lambda *_: {"executed": True})
    args = argparse.Namespace(
        sources=[str(source)],
        category="webinar",
        output_dir=str(output),
        target=None,
        quality_settings=None,
        include_25_fps=False,
        excerpts=1,
        excerpt_seconds=1,
        presets=None,
        dry_run=False,
        force=True,
    )
    assert bench.run(args)["executed"] is True
