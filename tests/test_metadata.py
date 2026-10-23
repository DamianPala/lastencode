"""Focused checks for metadata values stored in output files."""

from pathlib import Path

import pytest

from lastencode.metadata import format_iso6709, source_coordinates, verify_location_stripped


@pytest.mark.parametrize(
    "payload",
    [
        b"box data +37.7749-122.4194+15.0/ trailing",
        b"box data at 37.7749 trailing",
    ],
)
def test_stripped_location_search_detects_stored_coordinates(
    tmp_path: Path, payload: bytes
) -> None:
    work = tmp_path / "stripped.mp4"
    work.write_bytes(payload)
    coordinates = source_coordinates({"Keys:GPSCoordinates": "+37.7749-122.4194+15.0/"})

    with pytest.raises(ValueError, match="source coordinate string remains"):
        verify_location_stripped({}, work, coordinates)


def test_numeric_coordinates_are_formatted_with_altitude() -> None:
    coordinates = source_coordinates({"Keys:GPSCoordinates": "50.0613888889 19.9366 230"})

    assert coordinates.iso6709 == ()
    assert coordinates.position == (50.0613888889, 19.9366, 230.0)
    assert format_iso6709(coordinates.position) == "+50.06138889+19.93660000+230.00/"


def test_keys_iso6709_with_altitude_wins_over_udta_location() -> None:
    coordinates = source_coordinates(
        {
            "ffprobe:location": "+50.0614+019.9366/",
            "ffprobe:com.apple.quicktime.location.ISO6709": "+50.0614+019.9366+230.000/",
        }
    )

    assert coordinates.iso6709[0] == "+50.0614+019.9366+230.000/"
    assert coordinates.position == (50.0614, 19.9366, 230.0)


def test_numeric_southern_western_coordinates_keep_their_sign() -> None:
    tags = {
        "XMP-exif:GPSLatitude": -33.8688,
        "XMP-exif:GPSLongitude": -70.6693,
        "Composite:GPSLatitudeRef": "S",
        "Composite:GPSLongitudeRef": "W",
    }

    assert source_coordinates(tags).position == (-33.8688, -70.6693, None)
