"""Plain text presentation with visible provenance."""

from typing import cast

from lastencode.presets import table


def safe_text(value: object) -> str:
    return "".join(
        f"\\u{ord(char):04x}"
        if ord(char) < 32 or 127 <= ord(char) <= 159 or 0xD800 <= ord(char) <= 0xDFFF
        else char
        for char in str(value)
    )


def presets_text(document: object) -> str:
    data = table(document, "presets")
    categories = data["categories"]
    assert isinstance(categories, list)
    lines = ["Presets (provenance in brackets)"]
    for raw in cast(list[object], categories):
        category = table(raw, "category")
        lines += ["", safe_text(category["name"]) + ": " + safe_text(category["description"])]
        lines.append(f"Base: {safe_text(category['base'] or '-')}")
        location = table(category["location"], "location")
        lines.append("Location: " + setting_text(location))
        lines.append(f"{'Setting':30} | {'portable':50} | {'desktop':50}")
        targets = [table(category[target], target) for target in ("portable", "desktop")]
        for key in targets[0]:
            cells = [setting_text(table(target[key], key)) for target in targets]
            lines.append(f"{key:30} | {cells[0]:50} | {cells[1]:50}")
    return "\n".join(lines)


def setting_text(setting: dict[str, object]) -> str:
    value = setting["value"]
    displayed = (
        "-" if value is None else ("yes" if value else "no") if isinstance(value, bool) else value
    )
    return f"{safe_text(displayed)} [{safe_text(setting['origin'])}]"
