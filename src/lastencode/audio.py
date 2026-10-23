"""Audio decisions, with a bounded-memory full-stream dual-mono measurement."""

import array
import math
import subprocess
import sys
from pathlib import Path

from lastencode.probe import object_dict, stream_list
from lastencode.processes import tracked


def dual_mono(path: Path, index: int) -> bool:
    # AAC joint stereo is not necessarily sample-identical. -40 dB relative error
    # (1% RMS) tolerates its coding noise while rejecting meaningful stereo content.
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-i",
        str(path),
        "-map",
        f"0:{index}",
        "-vn",
        "-c:a",
        "pcm_f32le",
        "-f",
        "f32le",
        "pipe:1",
    ]
    energy = difference = 0.0
    with (
        subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process,
        tracked(process),
    ):
        assert process.stdout is not None
        try:
            while chunk := process.stdout.read(8 * 8192):
                samples = array.array("f")
                samples.frombytes(chunk)
                if sys.byteorder != "little":
                    samples.byteswap()
                for left, right in zip(samples[::2], samples[1::2], strict=True):
                    energy += (left * left + right * right) / 2
                    difference += (left - right) ** 2
            if process.wait():
                raise ValueError(f"ffmpeg: dual-mono analysis failed for audio stream {index}")
        except BaseException:
            process.kill()
            process.wait()
            raise
    return difference <= energy * 0.0001


def audio_arguments(
    path: Path, info: dict[str, object], settings: dict[str, object]
) -> tuple[list[str], list[dict[str, object]]]:
    arguments: list[str] = []
    decisions: list[dict[str, object]] = []
    for output_index, stream in enumerate(stream_list(info.get("audio_streams"))):
        index = int(str(stream["index"]))
        channels = int(str(stream.get("channels", 2)))
        conditional = settings["audio_channel_rule"] == "dual-mono-to-mono-otherwise-stereo"
        mono = conditional and (channels == 1 or (channels == 2 and dual_mono(path, index)))
        downmixed = channels in (3, 4)
        output_channels = 2 if downmixed else (1 if mono else channels)
        bitrate = int(
            str(settings["audio_dual_mono_bitrate_bps"] if mono else settings["audio_bitrate_bps"])
        )
        # Preset bitrate is a stereo budget; preserve surround at the same per-channel budget.
        if output_channels > 2:
            bitrate = math.ceil(bitrate * output_channels / 2)
        codec = "libopus" if settings["audio_codec"] == "opus" else "aac"
        suffix = f":a:{output_index}"
        arguments += [
            "-map",
            f"0:{index}",
            "-c" + suffix,
            codec,
            "-b" + suffix,
            str(bitrate),
            "-ac" + suffix,
            str(output_channels),
        ]
        if codec == "libopus":
            arguments += ["-application" + suffix, "audio"]
        tags = object_dict(stream.get("tags"))
        if tags.get("language"):
            arguments += ["-metadata:s" + suffix, f"language={tags['language']}"]
        dispositions = object_dict(stream.get("disposition"))
        disposition = "+".join(key for key, value in dispositions.items() if value) or "0"
        arguments += ["-disposition" + suffix, disposition]
        decisions.append(
            {
                "source_stream_index": index,
                "codec": settings["audio_codec"],
                "channels": output_channels,
                "bitrate_bps": bitrate,
                "dual_mono": bool(mono),
                "downmixed_to_stereo": downmixed,
                "source_channel_layout": stream.get("channel_layout"),
                "language": tags.get("language"),
                "disposition": dispositions,
            }
        )
    return arguments, decisions
