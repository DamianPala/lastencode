"""Shared input descriptors and JSON result schemas."""

from lastencode.preset_fields import FIELDS, MAX_CATEGORIES, MAX_FILE_BYTES, TARGETS

JSON_FLAG: dict[str, object] = {
    "name": "json",
    "type": "boolean",
    "required": False,
    "default": False,
    "description": "Select JSON for programmatic parsing; conflicts with --format.",
}
PRESETS_FLAG: dict[str, object] = {
    "name": "presets",
    "type": "string",
    "required": False,
    "description": (
        f"TOML preset file, at most {MAX_FILE_BYTES} bytes and {MAX_CATEGORIES} categories; "
        "replaces $XDG_CONFIG_HOME/lastencode/presets.toml (default ~/.config/lastencode/"
        "presets.toml), which is then not read; values the file does not set come from built-ins. "
        "Relative paths use the current directory. "
        "An absent default file is ignored; an absent explicit file is an error. "
        "Ignored by schema. Names use [a-z][a-z0-9-]{0,63}; new categories require base. "
        "Tables use categories.NAME and categories.NAME.TARGET; setting values use the "
        "value keys and units of presets JSON, without origin wrappers. "
        "Inheritance includes effective base overrides."
    ),
}
GLOBAL_FLAGS = [JSON_FLAG, PRESETS_FLAG]
FORMAT_FLAG: dict[str, object] = {
    "name": "format",
    "type": "string",
    "required": False,
    "enum": ["json", "text"],
    "description": "Select format; conflicts with --json; defaults by stdout TTY.",
}
EXIT_CODES = {
    "0": "Success: the command completed its documented operation.",
    "1": "Failure: at least one file failed, or the operation failed or was interrupted.",
    "2": "Usage error: invalid arguments or preset file.",
    "3": (
        "A required external tool is missing or unusable (too old, or "
        "lacking an encoder, filter or model)."
    ),
}


def object_schema(properties: dict[str, object]) -> dict[str, object]:
    return {"type": "object", "properties": properties, "required": list(properties)}


def setting_schema(value: dict[str, object]) -> dict[str, object]:
    return object_schema(
        {
            "value": value,
            "origin": {"type": "string", "description": "builtin or absolute preset file path."},
        }
    )


def presets_schema() -> dict[str, object]:
    settings: dict[str, object] = {}
    for name, spec in FIELDS.items():
        kind = {str: "string", int: "integer", bool: "boolean"}[spec.kind]
        value: dict[str, object] = {"type": kind, "description": spec.description}
        if spec.allow_native:
            value = {}
        elif name == "copy_video_below_bps":
            # O4 permits only nullable unions; this field can be integer or "never".
            value = {}
        elif spec.choices:
            value["enum"] = list(spec.choices)
        settings[name] = setting_schema(value) | {"description": spec.description}
    category = object_schema(
        {
            "name": {"type": "string"},
            "description": {"type": "string"},
            "base": {"type": ["string", "null"]},
            "location": setting_schema({"type": "string", "enum": ["keep", "strip"]}),
            **{target: object_schema(settings) for target in TARGETS},
        }
    )
    return object_schema(
        {
            "playback_targets": {
                "type": "array",
                "items": {"type": "string", "enum": list(TARGETS)},
            },
            "categories": {"type": "array", "items": category},
        }
    )


def bench_schema() -> dict[str, object]:
    row = object_schema(
        {
            "source": {"type": "string"},
            "excerpt_index": {"type": "integer"},
            "excerpt_start_seconds": {"type": "number"},
            "excerpt_seconds": {"type": "number"},
            "target": {"type": "string", "enum": list(TARGETS)},
            "quality_crf": {"type": "integer"},
            "frame_rate_change": {
                "type": "string",
                "description": "native, an explicit frame-rate variant, or the preset cap applied.",
            },
            "size_bytes": {"type": ["integer", "null"]},
            "bitrate_bps": {"type": ["number", "null"]},
            "encode_time_seconds": {"type": ["number", "null"]},
            "encode_time_realtime_multiple": {"type": ["number", "null"]},
            "vmaf_desktop_mean": {"type": ["number", "null"]},
            "vmaf_desktop_p5": {"type": ["number", "null"]},
            "vmaf_phone_mean": {"type": ["number", "null"]},
            "vmaf_phone_p5": {"type": ["number", "null"]},
            "xpsnr_y": {"type": ["number", "null"], "description": "XPSNR Y in dB."},
            "scaling": {"type": "string"},
            "dropped_frame_share": {"type": "number"},
            "valid": {"type": "boolean"},
            "reason": {"type": ["string", "null"]},
            "variant_path": {"type": ["string", "null"]},
            "side_by_side_path": {"type": ["string", "null"]},
        }
    )
    return object_schema(
        {
            "record_type": {"type": "string", "enum": ["bench_summary"]},
            "category": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "string"}},
            "excerpt_count": {"type": "integer"},
            "variant_count": {"type": "integer"},
            "encode_count": {"type": "integer"},
            "valid_count": {"type": "integer"},
            "invalid_count": {"type": "integer"},
            "dry_run": {"type": "boolean"},
            "changed": {"type": "boolean"},
            "requires_confirmation": {"type": "boolean"},
            "targets": {"type": "array", "items": target_schema()},
            "csv_path": {"type": "string"},
            "excerpt_paths": {"type": "array", "items": {"type": "string"}},
            "space_estimate_bytes": {"type": "integer"},
            "rows": {"type": "array", "items": row},
        }
    )


def target_schema() -> dict[str, object]:
    return object_schema(
        {
            "path": {"type": "string"},
            "effect": {"type": "string", "enum": ["create", "replace", "trash", "append"]},
            "size_bytes": {"type": ["integer", "null"]},
        }
    )
