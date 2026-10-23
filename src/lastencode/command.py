"""Command registration, independent of the root parser."""

import argparse
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class Command:
    name: str
    description: str
    configure: Callable[[argparse.ArgumentParser], None]
    run: Callable[[argparse.Namespace], object]
    args: list[dict[str, object]]
    flags: list[dict[str, object]]
    output: dict[str, object]
    output_description: str
    render_text: Callable[[object], str] = str
    effects: str = "read_only"
    stream: bool = False
    confirm: bool = False
    interactive: bool = False
    format_defaults: dict[str, str] | None = None

    exit_codes: dict[str, str] | None = None

    def detail(self) -> dict[str, object]:
        detail: dict[str, object] = {
            "name": self.name,
            "description": self.description,
            "args": self.args,
            "flags": self.flags,
            "effects": self.effects,
            "confirm": self.confirm,
            "interactive": self.interactive,
            "output": self.output,
            "output_description": self.output_description,
        }
        if self.exit_codes is not None:
            detail["exit_codes"] = self.exit_codes
        if self.stream:
            detail["stream"] = True
        if self.format_defaults is not None:
            detail["format_defaults"] = self.format_defaults
        return detail
