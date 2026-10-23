"""Published source and summary record vocabulary for convert NDJSON."""

from lastencode.contracts import object_schema, target_schema
from lastencode.preset_fields import FIELDS


def nullable(kind: str) -> dict[str, object]:
    return {"type": [kind, "null"]}


def string_array() -> dict[str, object]:
    return {"type": "array", "items": {"type": "string"}}


def convert_schema() -> dict[str, object]:
    # Source and summary records share one schema; record_type defines the fields in use.
    properties: dict[str, object] = {
        "changed": {"type": "boolean"},
        "next_to_source": {"type": "boolean"},
        "settings_fingerprint": nullable("string"),
        "source_ctime": nullable("string"),
        **trash_fields(),
        "tool_version": nullable("string"),
        "ffmpeg_version": nullable("string"),
        "encoder_version": nullable("string"),
        "started_at": nullable("string"),
        "ended_at": nullable("string"),
        "recovered": {"type": "boolean"},
        "verification_action": {"type": "string", "enum": ["encode", "copy-video", "copy-file"]},
        "skipped_count": {"type": "integer"},
        "recovered_count": {"type": "integer"},
        "remux_arguments": string_array(),
        "record_type": {"type": "string", "enum": ["source", "summary"]},
        "source_path": {"type": "string"},
        "output_path": {"type": "string"},
        "no_gain_path": {"type": "string"},
        "category": {"type": "string"},
        "target": {"type": "string", "enum": ["portable", "desktop"]},
        "settings": effective_settings_schema(),
        "warnings": string_array(),
        "action": {
            "type": "string",
            "enum": ["encode", "copy-video", "copy-file", "no-gain", "skip", "failure"],
        },
        "status": {"type": "string", "enum": ["planned", "failed", "completed"]},
        "reason": nullable("string"),
        "output_size_bytes": nullable("integer"),
        "source_sha256": nullable("string"),
        "output_sha256": nullable("string"),
        "video_bitrate_estimated": {"type": "boolean"},
        "encode_time_seconds": {"type": "number"},
        "check_time_seconds": {"type": "number"},
        "checks": {"type": "array", "items": {}},
        "failing_check": nullable("string"),
        "dropped_frame_share": nullable("number"),
        "frame_rate_cap": nullable("integer"),
        "frame_rate_change": nullable("string"),
        "video_copy_reason": nullable("string"),
        "failures": {"type": "array", "items": {}},
        "files": {"type": "array", "items": {}},
        "audio_decisions": {"type": ["array", "null"], "items": {}},
        "dropped_streams": {"type": ["array", "null"], "items": {}},
        "completed_count": {"type": "integer"},
        "source_size_bytes": nullable("integer"),
        "source_mtime": nullable("string"),
        "recording_date": nullable("string"),
        "date_source": nullable("string"),
        "location": {"type": ["string", "null"], "enum": ["kept", "stripped", None]},
        "gps_present": {"type": ["boolean", "null"]},
        "probe": probe_schema(),
        "no_gain_note": nullable("string"),
        "output_upper_bound_bytes": {"type": "integer"},
        "source_count": {"type": "integer"},
        "failed_count": {"type": "integer"},
        "ignored_paths": string_array(),
        "system_clutter_count": {"type": "integer"},
        "gps_outputs": string_array(),
        "space_needed_bytes": {"type": "integer"},
        "space_available_bytes": {"type": "integer"},
        "space_sufficient": {"type": "boolean"},
        "space_checked_path": {"type": "string"},
        "actions": {
            "type": "object",
            "required": [],
            "properties": {
                key: {"type": "integer"}
                for key in (
                    "encode",
                    "copy-video",
                    "copy-file",
                    "no-gain",
                    "skip",
                    "failure",
                )
            },
        },
    }
    return {
        "type": "object",
        "properties": properties,
        "required": ["record_type", "warnings", "changed"],
    }


def effective_settings_schema() -> dict[str, object]:
    properties: dict[str, object] = {
        name: (
            {}
            if field.allow_native
            else {"type": {str: "string", int: "integer", bool: "boolean"}[field.kind]}
        )
        for name, field in FIELDS.items()
    }
    properties["copy_video_below_bps"] = {}
    properties["location"] = {"type": "string", "enum": ["keep", "strip"]}
    return object_schema(properties) | {
        "description": "max_frame_rate is a positive integer fps or native; "
        "copy_video_below_bps is an integer bitrate or never."
    }


def probe_schema() -> dict[str, object]:
    properties: dict[str, object] = {
        name: nullable("string")
        for name in (
            "container",
            "video_codec",
            "pixel_format",
            "color_range",
            "color_transfer",
            "color_primaries",
            "color_space",
            "packet_frame_rate",
            "avg_frame_rate",
            "r_frame_rate",
            "creation_time",
            "keys_creation_date",
        )
    }
    properties.update(
        {
            "first_frame": first_frame_schema(),
            "warnings": string_array(),
            "maximum_window_frames": nullable("integer"),
            "video_end_seconds": nullable("number"),
            "container_start_seconds": {"type": "number"},
            "bit_depth": nullable("integer"),
            "rotation": {"type": "number"},
            "frame_rate_mode": {"type": "string", "enum": ["constant", "variable", "unknown"]},
            "video_bitrate_bps": nullable("number"),
            "video_bitrate_estimated": {"type": "boolean"},
            "duration_seconds": nullable("number"),
            # ffprobe stream dictionaries are external, format-dependent metadata.
            **{
                name: {"type": "array", "items": {}}
                for name in ("audio_streams", "subtitle_streams", "data_streams", "streams")
            },
        }
    )
    return object_schema(properties) | {"type": ["object", "null"]}


def first_frame_schema() -> dict[str, object]:
    # Empty until the decoded picture is read; ffprobe omits keys a frame does not carry.
    return {
        "type": "object",
        "properties": {
            "interlaced_frame": {"type": "integer"},
            "field_order": {"type": "string"},
            "sample_aspect_ratio": {"type": "string"},
            "color_range": {"type": "string"},
            "color_primaries": {"type": "string"},
            "color_transfer": {"type": "string"},
            "color_space": {"type": "string"},
            # Decoder side data (HDR mastering, light level, display matrix) as ffprobe names it.
            "side_data_list": {"type": "array", "items": {}},
            "duration_seconds": nullable("number"),
        },
        "required": [],
    }


def trash_schema() -> dict[str, object]:
    return {
        "type": ["object", "null"],
        "properties": {
            "status": {"type": "string", "enum": ["trashed", "kept"]},
            "path": nullable("string"),
            "reason": nullable("string"),
            "size_bytes": {"type": "integer"},
        },
        "required": ["status", "path", "reason"],
    }


def trash_fields() -> dict[str, object]:
    return {
        "trash_outcome": trash_schema(),
        "previous_output_trash": trash_schema(),
        "trashed_bytes": {"type": "integer"},
        "trash_space_note": {"type": "string"},
        "requires_confirmation": {"type": "boolean"},
        "trash_candidate_count": {"type": "integer"},
        "trash_candidate_bytes": {"type": "integer"},
        "targets": {
            "type": "array",
            "items": target_schema(),
        },
        "protected_outputs": string_array(),
    }
