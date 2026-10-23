"""Load built-in presets and resolve a strictly validated user overlay."""

import os
import re
import tomllib
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import cast

from lastencode.errors import InvalidInput
from lastencode.preset_fields import FIELDS, MAX_CATEGORIES, MAX_FILE_BYTES, TARGETS, Value


@dataclass(frozen=True)
class Setting:
    value: Value
    origin: str = "builtin"

    def document(self) -> dict[str, object]:
        return {"value": self.value, "origin": self.origin}


@dataclass
class Category:
    name: str
    description: str
    base: str | None
    location: Setting
    settings: dict[str, dict[str, Setting]]

    def document(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "base": self.base,
            "location": self.location.document(),
            **{
                target: {key: setting.document() for key, setting in settings.items()}
                for target, settings in self.settings.items()
            },
        }


def table(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise InvalidInput(f"{context}: expected a TOML table")
    return cast(dict[str, object], value)


def check_keys(data: dict[str, object], allowed: set[str], context: str) -> None:
    unknown = data.keys() - allowed
    if unknown:
        raise InvalidInput(
            f"{context}: unknown key {sorted(unknown)[0]!r}; "
            f"valid keys: {', '.join(sorted(allowed))}"
        )


def builtin_categories() -> dict[str, Category]:
    data = cast(
        dict[str, object],
        tomllib.loads(
            files("lastencode.data").joinpath("presets.toml").read_text(encoding="utf-8")
        ),
    )
    result: dict[str, Category] = {}
    for name, raw in table(data["categories"], "categories").items():
        entry = table(raw, name)
        category = Category(
            name,
            str(entry["description"]),
            None,
            Setting(str(entry["location"])),
            {},
        )
        for target in TARGETS:
            category.settings[target] = {
                key: Setting(
                    FIELDS[key].validate(value, f"{name}.{target}.{key}"),
                )
                for key, value in table(entry[target], f"{name}.{target}").items()
            }
        result[name] = category
    return result


def read_user_file(explicit: str | None) -> tuple[dict[str, object], str] | None:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    path = (
        Path(explicit).expanduser()
        if explicit is not None
        else config_home / "lastencode/presets.toml"
    )
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise InvalidInput(f"{path}: preset file exceeds {MAX_FILE_BYTES} bytes")
        data = cast(dict[str, object], tomllib.loads(raw.decode("utf-8")))
    except FileNotFoundError as error:
        if explicit is None:
            return None
        raise InvalidInput(f"--presets {path}: file does not exist") from error
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise InvalidInput(f"{path}: cannot read preset file: {error}") from error
    check_keys(data, {"categories"}, str(path))
    return table(data.get("categories", {}), str(path)), str(path.resolve())


def apply_values(category: Category, entry: dict[str, object], origin: str) -> None:
    context = f"{origin}: categories.{category.name}"
    check_keys(entry, {"base", "location", "description", *TARGETS}, context)
    if "location" in entry:
        value = entry["location"]
        if value not in ("keep", "strip"):
            raise InvalidInput(f"{context}.location: valid values: keep, strip; got {value!r}")
        category.location = Setting(str(value), origin)
    if "description" in entry:
        description = entry["description"]
        if not isinstance(description, str) or not description or "\n" in description:
            raise InvalidInput(f"{context}.description: expected a nonempty one-line string")
        category.description = description
    for target in TARGETS:
        if target not in entry:
            continue
        values = table(entry[target], f"{context}.{target}")
        check_keys(values, set(FIELDS), f"{context}.{target}")
        for key, raw in values.items():
            value = FIELDS[key].validate(raw, f"{context}.{target}.{key}")
            category.settings[target][key] = Setting(value, origin)


def resolve_categories(entries: dict[str, object], origin: str) -> list[Category]:
    builtins = builtin_categories()
    resolved: dict[str, Category] = {}
    active: set[str] = set()

    def resolve(name: str) -> Category:
        if name in resolved:
            return resolved[name]
        if name in active:
            raise InvalidInput(f"{origin}: cyclic category base involving {name!r}")
        if name not in entries and name not in builtins:
            valid = ", ".join(sorted(builtins.keys() | entries.keys()))
            raise InvalidInput(f"{origin}: unknown base {name!r}; valid values: {valid}")
        active.add(name)
        entry = table(entries.get(name, {}), f"{origin}: categories.{name}")
        base = entry.get("base")
        if base is not None and not isinstance(base, str):
            raise InvalidInput(f"{origin}: categories.{name}.base: expected str")
        if name not in builtins and not base:
            raise InvalidInput(f"{origin}: new category {name!r} requires an existing base")
        parent = resolve(base) if isinstance(base, str) else builtins[name]
        category = Category(
            name,
            parent.description,
            base,
            parent.location,
            {target: settings.copy() for target, settings in parent.settings.items()},
        )
        apply_values(category, entry, origin)
        resolved[name] = category
        active.remove(name)
        return category

    for name in category_names(entries.keys() | builtins.keys(), origin):
        resolve(name)
    return [resolved[name] for name in sorted(resolved)]


def category_names(names: set[str], origin: str) -> list[str]:
    if len(names) > MAX_CATEGORIES:
        raise InvalidInput(f"{origin}: at most {MAX_CATEGORIES} categories are supported")
    for name in names:
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name):
            raise InvalidInput(
                f"{origin}: invalid category name {name!r}; use [a-z][a-z0-9-]{{0,63}}"
            )
    return sorted(names)


def load_categories(explicit: str | None = None) -> list[Category]:
    overlay = read_user_file(explicit)
    return resolve_categories(*overlay) if overlay else resolve_categories({}, "builtin")
