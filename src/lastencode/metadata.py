"""Write and read back recording metadata on an MP4 work file."""

import json
import math
import os
import re
import struct
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import BinaryIO

from lastencode.dates import parse_date
from lastencode.identity import tag_payload
from lastencode.platform_io import replace_retry, unlink_retry
from lastencode.probe import light_probe, object_dict, stream_list
from lastencode.processes import run
from lastencode.tools import capture

LOCATION_DELETE_OPTIONS = [
    "-GPS:all=",
    "-XMP:GPS*=",
    "-XMP:Location*=",
    "-XMP:Sublocation=",
    "-XMP:City=",
    "-XMP:State=",
    "-XMP:Country=",
    "-XMP:CountryCode=",
    "-Keys:GPSCoordinates=",
    "-UserData:GPSCoordinates=",
    "-ItemList:GPSCoordinates=",
    "-Keys:com.apple.quicktime.location.ISO6709=",
    # Apple location keys (LocationName, LocationAccuracyHorizontal, ...) arrive via -Keys:all.
    "-Keys:Location*=",
    "-Keys:location=",
    "-Keys:location-eng=",
]

ISO_6709 = re.compile(
    r"^([+-](?:\d+(?:\.\d*)?|\.\d+))"
    r"([+-](?:\d+(?:\.\d*)?|\.\d+))"
    r"([+-](?:\d+(?:\.\d*)?|\.\d+))?/?$"
)


@dataclass(frozen=True)
class SourceCoordinates:
    iso6709: tuple[str, ...]
    position: tuple[float, float, float | None] | None

    @property
    def present(self) -> bool:
        return bool(self.iso6709 or self.position is not None)


def exiftool_tags(path: Path) -> dict[str, object]:
    raw = capture(["exiftool", "-n", "-j", "-G1", "-a", "-s", "-api", "QuickTimeUTC=1", str(path)])
    document: object = json.loads(raw)
    entries = stream_list(document)
    if not entries:
        raise ValueError(f"exiftool: no metadata read from {path}")
    return entries[0]


def source_coordinates(tags: dict[str, object]) -> SourceCoordinates:
    values = coordinate_values(tags)
    raw_iso = tuple(dict.fromkeys(value for value in values if parse_iso6709(value)))
    position = next((parsed for value in raw_iso if (parsed := parse_iso6709(value))), None)
    if position is None:
        position = numeric_position(tags)
    if position is None:
        position = next((parsed for value in values if (parsed := decimal_position(value))), None)
    return SourceCoordinates(raw_iso, position)


def coordinate_values(tags: dict[str, object]) -> list[str]:
    selected: list[tuple[int, str]] = []
    for name, value in tags.items():
        lowered = name.casefold()
        leaf = lowered.split(":")[-1]
        if (
            leaf == "gpscoordinates" or "iso6709" in leaf or leaf in {"location", "location-eng"}
        ) and value not in (None, ""):
            # Keys (Apple ISO 6709, often with altitude) before udta ©xyz/loci forms.
            keys_form = lowered.startswith("keys:") or "iso6709" in leaf
            selected.append((0 if keys_form else 1, str(value).strip()))
    selected.sort(key=lambda item: item[0])
    return list(dict.fromkeys(value for _, value in selected))


def format_location_tags(path: Path) -> dict[str, object]:
    raw = capture(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format_tags=location,location-eng,com.apple.quicktime.location.ISO6709",
            "-of",
            "json",
            str(path),
        ]
    )
    document: object = json.loads(raw)
    format_info = object_dict(object_dict(document).get("format"))
    tags = object_dict(format_info.get("tags"))
    return {f"ffprobe:{name}": value for name, value in tags.items()}


def parse_iso6709(value: str) -> tuple[float, float, float | None] | None:
    match = ISO_6709.fullmatch(value.strip())
    if match is None:
        return None
    latitude, longitude = float(match[1]), float(match[2])
    if not valid_latitude_longitude(latitude, longitude):
        return None
    altitude = float(match[3]) if match[3] is not None else None
    return latitude, longitude, altitude


def numeric_position(tags: dict[str, object]) -> tuple[float, float, float | None] | None:
    latitude = numeric_tag(tags, "gpslatitude")
    longitude = numeric_tag(tags, "gpslongitude")
    if latitude is None or longitude is None:
        for name, value in tags.items():
            if name.casefold().endswith(":gpsposition"):
                position = decimal_position(str(value))
                if position is not None:
                    return position
        return None
    latitude = apply_reference(latitude, string_tag(tags, "gpslatituderef"), "south")
    longitude = apply_reference(longitude, string_tag(tags, "gpslongituderef"), "west")
    if not valid_latitude_longitude(latitude, longitude):
        return None
    altitude = numeric_tag(tags, "gpsaltitude")
    if altitude is not None and string_tag(tags, "gpsaltituderef") in {"1", "Below Sea Level"}:
        altitude = -abs(altitude)
    return latitude, longitude, altitude


def numeric_tag(tags: dict[str, object], suffix: str) -> float | None:
    for name, value in tags.items():
        if name.split(":")[-1].casefold() != suffix or value in (None, ""):
            continue
        try:
            number = float(str(value))
        except ValueError:
            continue
        if math.isfinite(number):
            return number
    return None


def string_tag(tags: dict[str, object], suffix: str) -> str | None:
    for name, value in tags.items():
        if name.split(":")[-1].casefold() == suffix and value not in (None, ""):
            return str(value)
    return None


def apply_reference(value: float, reference: str | None, negative: str) -> float:
    if reference is None:
        return value
    # exiftool -n gives "S"/"W", the print form "South"/"West": compare the first letter.
    return -abs(value) if reference.strip().casefold()[:1] == negative[:1] else abs(value)


def valid_latitude_longitude(latitude: float, longitude: float) -> bool:
    return abs(latitude) <= 90 and abs(longitude) <= 180


def decimal_position(value: str) -> tuple[float, float, float | None] | None:
    numbers = re.findall(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value)
    if len(numbers) < 2:
        return None
    latitude, longitude = float(numbers[0]), float(numbers[1])
    if not valid_latitude_longitude(latitude, longitude):
        return None
    altitude = float(numbers[2]) if len(numbers) > 2 else None
    return latitude, longitude, altitude


def android_tags(tags: dict[str, object]) -> dict[str, object]:
    names = {
        "androidversion",
        "androidmake",
        "androidmanufacturer",
        "androidmodel",
        "androidutcoffset",
        "androidtimezone",
    }
    return {
        name: value
        for name, value in tags.items()
        if name.casefold().startswith("keys:")
        and (
            "com.android." in name.casefold()
            or "com.samsung." in name.casefold()
            or name.split(":", 1)[-1].casefold().replace("_", "") in names
            or name.split(":", 1)[-1].casefold()
            in {"version", "manufacturer", "model", "utc_offset"}
        )
    }


def format_iso6709(position: tuple[float, float, float | None] | None) -> str:
    if position is None:
        raise ValueError(
            "metadata: cannot write coordinates without numeric latitude and longitude"
        )
    latitude, longitude, altitude = position
    value = f"{latitude:+.8f}{longitude:+.8f}"
    if altitude is not None:
        value += f"{altitude:+.2f}"
    return value + "/"


def write_tags(
    source: Path,
    work: Path,
    location: str,
    coordinates: SourceCoordinates,
    identity: dict[str, object] | None = None,
) -> None:
    command = [
        "exiftool",
        "-config",
        str(Path(__file__).parent / "data" / "exiftool.config"),
        "-overwrite_original",
        "-api",
        "QuickTimeUTC=1",
        "-TagsFromFile",
        str(source),
        "-Keys:all",
    ]
    if location == "stripped":
        command.extend(LOCATION_DELETE_OPTIONS)
    elif coordinates.present:
        value = (
            coordinates.iso6709[0] if coordinates.iso6709 else format_iso6709(coordinates.position)
        )
        command.extend((f"-Keys:GPSCoordinates={value}", f"-UserData:GPSCoordinates={value}"))
    if identity is not None:
        command.append("-Keys:LastEncode=" + json.dumps(identity, separators=(",", ":")))
    command.append(str(work))
    run_external(command, "exiftool")


def run_external(command: list[str], name: str) -> None:
    try:
        result = run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        raise ValueError(f"{name}: {error}") from error
    if result.returncode:
        details = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise ValueError(f"{name}: {details}")


def date_headers(tags: dict[str, object], recording_date: str) -> None:
    expected = parse_date(recording_date)
    if expected is None:
        raise ValueError(f"invalid planned recording date: {recording_date!r}")
    required = {
        "CreateDate",
        "ModifyDate",
        "TrackCreateDate",
        "TrackModifyDate",
        "MediaCreateDate",
        "MediaModifyDate",
    }
    found: dict[str, list[object]] = {}
    for name, value in tags.items():
        field = name.split(":")[-1]
        if field in required:
            found.setdefault(field, []).append(value)
    missing = required - found.keys()
    if missing:
        raise ValueError(
            f"metadata read-back: missing MP4 date headers: {', '.join(sorted(missing))}"
        )
    for name, values in found.items():
        for value in values:
            parsed = parse_date(str(value))
            if parsed != expected:
                raise ValueError(
                    f"metadata read-back: {name} is {value!r}, expected {recording_date}"
                )


def verify_metadata(
    source_tags: dict[str, object],
    output_tags: dict[str, object],
    source_probe: dict[str, object],
    work: Path,
    record: dict[str, object],
    coordinates: SourceCoordinates,
) -> bool:
    recording_date = str(record["recording_date"])
    date_headers(output_tags, recording_date)
    output_probe = light_probe(work)
    actual_date = parse_date(str(output_probe.get("creation_time") or ""))
    if actual_date != parse_date(recording_date):
        raise ValueError(
            f"metadata read-back: creation_time is {output_probe.get('creation_time')!r}, "
            f"expected {recording_date}"
        )
    source_creation = source_tags.get("Keys:CreationDate")
    if source_creation is not None and output_tags.get("Keys:CreationDate") != source_creation:
        raise ValueError("metadata read-back: Keys:CreationDate did not survive unchanged")
    if android_tags(source_tags) != android_tags(output_tags):
        raise ValueError("metadata read-back: Android capture tags did not survive unchanged")
    verify_languages(source_probe, output_probe)
    return verify_location(output_tags, work, str(record["location"]), coordinates)


def verify_location(
    output_tags: dict[str, object],
    work: Path,
    location: str,
    coordinates: SourceCoordinates,
) -> bool:
    if location == "stripped":
        verify_location_stripped(output_tags, work, coordinates)
        return False
    if coordinates.present:
        verify_location_kept(output_tags, coordinates)
        return True
    return False


def verify_location_kept(tags: dict[str, object], coordinates: SourceCoordinates) -> None:
    expected = coordinates.position
    if expected is None:
        raise ValueError("metadata read-back: source coordinates have no numeric position")
    for group in ("Keys", "UserData"):
        actual = tags.get(f"{group}:GPSCoordinates")
        actual_position = (
            parse_coordinate_position(str(actual)) if actual not in (None, "") else None
        )
        if actual_position is None:
            raise ValueError(
                f"metadata read-back: {group}:GPSCoordinates has no numeric coordinate value"
            )
        compare_positions(actual_position, expected, group)


def verify_languages(source: dict[str, object], output: dict[str, object]) -> None:
    source_streams = stream_list(source.get("streams"))
    output_streams = stream_list(output.get("streams"))
    source_videos = [
        s
        for s in source_streams
        if s.get("codec_type") == "video"
        and not object_dict(s.get("disposition")).get("attached_pic")
    ]
    output_videos = [
        s
        for s in output_streams
        if s.get("codec_type") == "video"
        and not object_dict(s.get("disposition")).get("attached_pic")
    ]
    if source_videos and output_videos:
        compare_language(source_videos[0], output_videos[0], "video")
    source_audio = [s for s in source_streams if s.get("codec_type") == "audio"]
    output_audio = [s for s in output_streams if s.get("codec_type") == "audio"]
    if len(source_audio) != len(output_audio):
        raise ValueError(f"metadata read-back: audio stream count changed to {len(output_audio)}")
    for index, (left, right) in enumerate(zip(source_audio, output_audio, strict=True)):
        compare_language(left, right, f"audio stream {index}")


def compare_language(source: dict[str, object], output: dict[str, object], label: str) -> None:
    source_language = object_dict(source.get("tags")).get("language")
    output_language = object_dict(output.get("tags")).get("language")
    if source_language is not None and output_language != source_language:
        raise ValueError(
            f"metadata read-back: {label} language is {output_language!r}, "
            f"expected {source_language!r}"
        )


def compare_positions(
    actual: tuple[float, float, float | None],
    expected: tuple[float, float, float | None],
    group: str,
) -> None:
    actual_latitude, actual_longitude, actual_altitude = actual
    expected_latitude, expected_longitude, expected_altitude = expected
    if (
        abs(actual_latitude - expected_latitude) > 1e-5
        or abs(actual_longitude - expected_longitude) > 1e-5
    ):
        raise ValueError(
            f"metadata read-back: {group}:GPSCoordinates is {actual!r}, expected {expected!r}"
        )
    if expected_altitude is not None and (
        actual_altitude is None or abs(actual_altitude - expected_altitude) > 0.1
    ):
        raise ValueError(
            f"metadata read-back: {group}:GPSCoordinates altitude is {actual_altitude!r}, "
            f"expected {expected_altitude!r} within 0.1 m"
        )


def coordinate_search_terms(coordinates: SourceCoordinates) -> tuple[str, ...]:
    terms = list(coordinates.iso6709)
    if coordinates.position is not None:
        latitude, longitude, _ = coordinates.position
        for coordinate in (latitude, longitude):
            truncated = Decimal(str(abs(coordinate))).quantize(
                Decimal("0.0001"), rounding=ROUND_DOWN
            )
            terms.append(f"{truncated:.4f}")
    return tuple(dict.fromkeys(terms))


def parse_coordinate_position(value: str) -> tuple[float, float, float | None] | None:
    return parse_iso6709(value) or decimal_position(value)


def verify_location_stripped(
    tags: dict[str, object], work: Path, coordinates: SourceCoordinates
) -> None:
    location_tags = [
        name
        for name in tags
        if any(word in name.casefold() for word in ("gps", "location", "iso6709", "loci"))
    ]
    if location_tags:
        raise ValueError(
            "metadata read-back: GPS or location tags remain: " + ", ".join(location_tags)
        )
    for term in coordinate_search_terms(coordinates):
        if contains_bytes(work, term.encode("utf-8")):
            raise ValueError(
                "metadata read-back: source coordinate string remains in stripped output"
            )


def contains_bytes(path: Path, needle: bytes) -> bool:
    overlap = b""
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            data = overlap + chunk
            if needle in data:
                return True
            overlap = data[-max(0, len(needle) - 1) :]
    return False


def mp4_box(stream: BinaryIO, offset: int, file_size: int) -> tuple[int, bytes] | None:
    stream.seek(offset)
    header = stream.read(8)
    if len(header) != 8:
        return None
    box_size, box_type = struct.unpack(">I4s", header)
    header_size = 8
    if box_size == 1:
        extended = stream.read(8)
        if len(extended) != 8:
            return None
        box_size = struct.unpack(">Q", extended)[0]
        header_size = 16
    elif box_size == 0:
        box_size = file_size - offset
    if box_size < header_size or offset + box_size > file_size:
        return None
    return box_size, box_type


def is_faststart(path: Path) -> bool:
    size = path.stat().st_size
    offset = 0
    moov = mdat = None
    with path.open("rb") as stream:
        while offset + 8 <= size:
            box = mp4_box(stream, offset, size)
            if box is None:
                return False
            box_size, box_type = box
            if box_type == b"moov" and moov is None:
                moov = offset
            elif box_type == b"mdat" and mdat is None:
                mdat = offset
            offset += box_size
    return moov is not None and mdat is not None and moov < mdat


def remux_faststart(work: Path, recording_date: str, location: str) -> None:
    remux = work.with_name(f"{work.stem}.faststart{work.suffix}")
    if os.path.lexists(remux):
        raise ValueError(f"Faststart work path already exists: {remux}; remove it before retrying")
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-nostdin",
        "-n",
        "-i",
        str(work),
        "-map",
        "0",
        "-map_metadata",
        "0",
        "-map_chapters",
        "0",
        "-c",
        "copy",
        "-metadata",
        f"creation_time={recording_date}",
    ]
    if location == "stripped":
        command.extend(("-metadata", "location=", "-metadata", "location-eng="))
    command.extend(("-movflags", "+faststart", "-write_tmcd", "0", "-f", "mp4", str(remux)))
    try:
        run_external(command, "ffmpeg faststart remux")
        replace_retry(remux, work)
    finally:
        unlink_retry(remux, missing_ok=True)


def apply_metadata(source: Path, work: Path, record: dict[str, object]) -> None:
    source_tags = exiftool_tags(source)
    coordinates = source_coordinates(source_tags | format_location_tags(source))
    source_probe = object_dict(record.get("probe"))
    write_tags(source, work, str(record["location"]), coordinates, tag_payload(record))
    output_tags = exiftool_tags(work)
    gps_present = verify_metadata(source_tags, output_tags, source_probe, work, record, coordinates)
    if not is_faststart(work):
        remux_faststart(work, str(record["recording_date"]), str(record["location"]))
        write_tags(source, work, str(record["location"]), coordinates, tag_payload(record))
        output_tags = exiftool_tags(work)
        gps_present = verify_metadata(
            source_tags, output_tags, source_probe, work, record, coordinates
        )
        if not is_faststart(work):
            raise ValueError(
                "metadata step: MP4 index remains after media data after faststart remux"
            )
    written = exiftool_tags(work)
    raw = next((v for k, v in written.items() if k.split(":")[-1] == "LastEncode"), None)
    if not isinstance(raw, str) or json.loads(raw) != tag_payload(record):
        raise ValueError("LastEncode tag read-back does not match source identity")
    record["gps_present"] = gps_present
