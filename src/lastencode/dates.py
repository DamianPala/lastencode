"""Pure recording-date selection shared by planning and future metadata writing."""

import calendar
import os
import re
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from lastencode.errors import InvalidInput


def local_zone(name: str | None) -> tzinfo:
    if name is not None:
        try:
            return ZoneInfo(name)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise InvalidInput(f"--tz {name!r}: expected an installed IANA time zone") from error
    configured = os.environ.get("TZ", "").removeprefix(":")
    if configured:
        return local_zone(configured)
    # Reading tzfile retains historical and future DST transitions (unlike astimezone().tzinfo).
    with Path("/etc/localtime").open("rb") as stream:
        return ZoneInfo.from_file(stream)


def utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for candidate in value.split(";"):
        normalized = re.sub(r"^(\d{4}):(\d{2}):(\d{2})", r"\1-\2-\3", candidate.strip())
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def filename_date(name: str, zone: tzinfo) -> datetime | None:
    patterns = (
        (r"(?<!\d)(\d{8}_\d{6})(?!\d)", "%Y%m%d_%H%M%S"),
        (r"VID(\d{14})(?!\d)", "%Y%m%d%H%M%S"),
        (r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)", "%Y-%m-%d"),
    )
    for pattern, date_format in patterns:
        match = re.search(pattern, name)
        if match:
            try:
                # fold=0 selects the pre-transition (earlier) offset for overlaps and gaps.
                return datetime.strptime(match[1], date_format).replace(tzinfo=zone, fold=0)
            except ValueError:
                continue
    return None


def recording_date(
    creation_time: str | None, keys_date: str | None, name: str, mtime: float, zone: tzinfo
) -> tuple[str, str]:
    for raw, source in ((creation_time, "creation_time"), (keys_date, "Keys:CreationDate")):
        parsed = parse_date(raw)
        if parsed is not None:
            return utc_text(parsed.replace(microsecond=0)), source
    named = filename_date(name, zone)
    if named is not None:
        return utc_text(named.replace(microsecond=0)), "filename"
    return utc_text(datetime.fromtimestamp(mtime, UTC).replace(microsecond=0)), "mtime"


def ns_text(value: int) -> str:
    seconds, fraction = divmod(value, 1_000_000_000)
    date = datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{date}.{fraction:09d}Z"


def text_ns(value: object) -> int:
    """Read our UTC nanosecond timestamps without rounding through float/microseconds."""
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.(\d{9})Z", str(value))
    if match is None:
        raise ValueError(f"Invalid UTC nanosecond timestamp: {value!r}")
    date = datetime.strptime(match[1], "%Y-%m-%dT%H:%M:%S")
    return calendar.timegm(date.timetuple()) * 1_000_000_000 + int(match[2])
