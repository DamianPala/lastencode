"""Discovery and conservative collision checks, without creating paths."""

import fnmatch
from dataclasses import dataclass
from pathlib import Path

from lastencode.errors import InvalidInput, NotFound

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".m4v", ".avi", ".webm", ".ts", ".mpg", ".mpeg"}
SYSTEM_CLUTTER_DIRS = {
    "@eaDir",
    "#recycle",
    "#snapshot",
    ".SynologyWorkingDirectory",
}
SYSTEM_CLUTTER_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}


@dataclass(frozen=True)
class Source:
    path: Path
    root: Path
    output: Path
    no_gain: Path

    @property
    def is_video(self) -> bool:
        return self.path.suffix.lower() in VIDEO_EXTENSIONS


def folded(path: Path) -> tuple[str, ...]:
    # Case-fold component by component, including nonexistent output suffixes.
    return tuple(part.casefold() for part in path.resolve().parts)


def inside(path: Path, parent: Path) -> bool:
    prefix = folded(parent)
    return folded(path)[: len(prefix)] == prefix


def ignored_name(path: Path) -> bool:
    return path.name == "lastencode-manifest.jsonl" or fnmatch.fnmatchcase(
        path.name, ".*.lastencode-part.*"
    )


def is_system_clutter(path: Path) -> bool:
    if path.is_dir():
        return path.name in SYSTEM_CLUTTER_DIRS or path.name.startswith(".Trash-")
    return path.name in SYSTEM_CLUTTER_FILES or path.name.startswith("._")


def walk(path: Path, output: Path, ancestors: frozenset[Path] = frozenset()) -> list[Path]:
    if is_system_clutter(path):
        return [path]
    if not path.is_dir():
        return [path]
    if inside(output, path):
        raise InvalidInput(f"output folder {output} is inside input folder {path}")
    resolved = path.resolve()
    if resolved in ancestors:
        return []
    found: list[Path] = [path]
    for child in sorted(path.iterdir()):
        found.extend(walk(child, output, ancestors | {resolved}))
    return found


def discover(inputs: list[str], output: Path) -> tuple[list[Source], list[str]]:
    validate_inputs(inputs)
    sources: list[Source] = []
    ignored: list[str] = []
    roots: set[Path] = set()
    for value in inputs:
        path = Path(value).absolute()
        if not path.exists():
            raise NotFound(f"source {path}: does not exist")
        root = path if path.is_dir() else path.parent
        if inside(output, root):
            raise InvalidInput(
                f"output folder {output} is inside input folder {root} (source {path})"
            )
        roots.add(root)
        for item in walk(path, output):
            if item.is_dir():
                if is_system_clutter(item):
                    ignored.append(str(item))
                    continue
                roots.add(item)
                continue
            if ignored_name(item) or is_system_clutter(item):
                ignored.append(str(item))
                continue
            mirror = output / item.relative_to(root)
            encoded = (
                mirror.with_suffix(".mp4") if item.suffix.lower() in VIDEO_EXTENSIONS else mirror
            )
            sources.append(Source(item, root, encoded, mirror))
    validate_paths(sources, output, roots)
    return sources, ignored


def validate_paths(sources: list[Source], output: Path, roots: set[Path]) -> None:
    claimed: dict[str, Source] = {}
    # Resolve once and test prefixes, so large trees stay linear instead of quadratic.
    trees = {folded(root): root for root in roots}
    originals = {folded(source.path): source.path for source in sources}
    for source in sources:
        for candidate in {source.output, source.no_gain}:
            if candidate.relative_to(output).parts[0].casefold() in {
                ".lastencode.lock",
                "lastencode-manifest.jsonl",
            }:
                raise InvalidInput(
                    f"output path {candidate} is reserved for the run lock or manifest"
                )
            validate_destination(candidate, trees, originals)
            claim_path(candidate, source, claimed)
    # A file output cannot also be a parent directory of another output.
    for key, source in claimed.items():
        for parent in Path(key).parents:
            if str(parent) in claimed:
                other = claimed[str(parent)]
                raise InvalidInput(f"output collision: {source.path} and {other.path}: {key}")
    if output.exists() and not output.is_dir():
        raise InvalidInput(f"output folder {output}: is not a directory")


def claim_path(candidate: Path, source: Source, claimed: dict[str, Source]) -> None:
    key = str(candidate.resolve()).casefold()
    previous = claimed.get(key)
    if previous is not None and previous is not source:
        raise InvalidInput(
            f"output collision: {previous.path} and {source.path} may both write {candidate}"
        )
    claimed[key] = source


def validate_destination(
    candidate: Path, trees: dict[tuple[str, ...], Path], originals: dict[tuple[str, ...], Path]
) -> None:
    parts = folded(candidate)
    prefixes = [parts[:length] for length in range(1, len(parts) + 1)]
    for prefix in prefixes:
        if prefix in trees:
            raise InvalidInput(f"output path {candidate} lies inside source tree {trees[prefix]}")
    for prefix in prefixes:
        if prefix in originals:
            raise InvalidInput(f"output path {candidate} overlaps source {originals[prefix]}")


def validate_inputs(inputs: list[str]) -> None:
    paths = [Path(value).absolute() for value in inputs]
    for index, path in enumerate(paths):
        for previous in paths[:index]:
            same = folded(path) == folded(previous)
            nested = (previous.is_dir() and inside(path, previous)) or (
                path.is_dir() and inside(previous, path)
            )
            if same or nested:
                raise InvalidInput(f"overlapping inputs: {previous} and {path}")
