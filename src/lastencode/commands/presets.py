"""The read-only preset listing command."""

import argparse

from lastencode.command import Command
from lastencode.contracts import FORMAT_FLAG, presets_schema
from lastencode.preset_fields import MAX_CATEGORIES, TARGETS
from lastencode.presets import load_categories
from lastencode.render import presets_text


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=["json", "text"], help=str(FORMAT_FLAG["description"]))


def run(args: argparse.Namespace) -> object:
    explicit: str | None = args.presets
    return {
        "playback_targets": list(TARGETS),
        "categories": [category.document() for category in load_categories(explicit)],
    }


COMMAND = Command(
    name="presets",
    description=(
        f"List effective presets, sorted by category name (at most {MAX_CATEGORIES} categories)."
    ),
    configure=configure,
    run=run,
    args=[],
    flags=[FORMAT_FLAG],
    output=presets_schema(),
    output_description=(
        "All categories and both targets; no pagination or truncation. "
        "Each setting has value and origin. base is null for built-ins unless explicitly set. "
        "An integer copy_video_below_bps is a bitrate in bits per second; never disables copying. "
        "A conditional audio rule uses audio_dual_mono_bitrate_bps for dual-mono sources and "
        "audio_bitrate_bps otherwise. Text includes origins."
    ),
    render_text=presets_text,
)
