"""Discovery and conservative collision checks, without creating paths."""

import fnmatch
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from lastencode.errors import InvalidInput, NotFound

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".m4v", ".avi", ".webm", ".ts", ".mpg", ".mpeg"}
SYSTEM_CLUTTER_DIRS = {
    "@eaDir",
    "#recycle",
    "#snapshot",
    ".SynologyWorkingDirectory",
    "$RECYCLE.BIN",
    "System Volume Information",
    ".Trashes",
    ".Spotlight-V100",
    ".fseventsd",
    ".TemporaryItems",
    ".DocumentRevisions-V100",
}
SYSTEM_CLUTTER_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}


@dataclass(frozen=True)
class Source:
    path: Path
    root: Path
    output: Path
    no_gain: Path
    next_to_source: bool = False

    @property
    def is_video(self) -> bool:
        return self.path.suffix.lower() in VIDEO_EXTENSIONS


def folded(path: Path) -> tuple[str, ...]:
    # Case-fold component by component, including nonexistent output suffixes.
    return tuple(unicodedata.normalize("NFD", part).casefold() for part in path.resolve().parts)


def inside(path: Path, parent: Path) -> bool:
    prefix = folded(parent)
    return folded(path)[: len(prefix)] == prefix


def ignored_name(path: Path) -> bool:
    return path.name in {"lastencode-manifest.jsonl", ".lastencode.lock"} or fnmatch.fnmatchcase(
        path.name, ".*.lastencode-part.*"
    )


def is_system_clutter(path: Path) -> bool:
    name = path.name.casefold()
    if path.is_dir():
        return name in {item.casefold() for item in SYSTEM_CLUTTER_DIRS} or name.startswith(
            ".trash-"
        )
    return name in {item.casefold() for item in SYSTEM_CLUTTER_FILES} or name.startswith("._")


def walk(path: Path, output: Path | None, ancestors: frozenset[Path] = frozenset()) -> list[Path]:
    if is_system_clutter(path):
        return [path]
    if not path.is_dir():
        return [path]
    if output is not None and inside(output, path):
        raise InvalidInput(
            f"output folder {output} is inside input folder {path}; "
            "choose an output folder outside it"
        )
    resolved = path.resolve()
    if resolved in ancestors:
        return []
    found: list[Path] = [path]
    for child in sorted(path.iterdir()):
        found.extend(walk(child, output, ancestors | {resolved}))
    return found


def run_root(inputs: list[str]) -> Path:
    validate_inputs(inputs)
    paths = [Path(value).absolute() for value in inputs]
    for path in paths:
        if not path.exists():
            raise NotFound(f"source {path}: does not exist")
    folders = [path if path.is_dir() else path.parent for path in paths]
    # File identity holds across symlinks and file systems that ignore letter case.
    roots = {(info.st_dev, info.st_ino) for info in map(os.stat, folders)}
    if len(roots) != 1 or (len(paths) > 1 and any(path.is_dir() for path in paths)):
        raise InvalidInput("without --output-dir, use one folder or files in one folder")
    root = folders[0]
    if not os.access(root, os.W_OK | os.X_OK):
        raise InvalidInput(f"run root {root} is not writable; choose --output-dir")
    return root


def earlier_output(path: Path) -> bool:
    # Local import keeps the Source data model independent of conflict planning.
    from lastencode.conflicts import output_tag

    return path.suffix.lower() in VIDEO_EXTENSIONS and output_tag(path) is not None


def discover(inputs: list[str], output: Path | None) -> tuple[list[Source], list[str]]:
    destination = output if output is not None else run_root(inputs)
    validate_inputs(inputs)
    sources: list[Source] = []
    ignored: list[str] = []
    roots: set[Path] = set()
    for value in inputs:
        path = Path(value).absolute()
        if not path.exists():
            raise NotFound(f"source {path}: does not exist")
        root = path if path.is_dir() else path.parent
        if path.is_dir():
            roots.add(root)
        found, excluded = discover_root(path, root, output)
        if output is not None and found:
            validate_output_folder(path, output)
        sources.extend(found)
        ignored.extend(excluded)
    validate_paths(sources, destination, roots if output is not None else set())
    return sources, ignored


def discover_root(path: Path, root: Path, output: Path | None) -> tuple[list[Source], list[str]]:
    sources: list[Source] = []
    ignored: list[str] = []
    for item in walk(path, output):
        if item.is_dir():
            if is_system_clutter(item):
                ignored.append(str(item))
            continue
        if ignored_name(item) or is_system_clutter(item) or earlier_output(item):
            ignored.append(str(item))
            continue
        if output is None and item.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        sources.append(source_paths(item, root, output))
    return sources, ignored


def source_paths(item: Path, root: Path, output: Path | None) -> Source:
    if output is None:
        encoded = item.with_name(f"{item.stem}.lastencode.mp4")
        return Source(item, root, encoded, encoded, next_to_source=True)
    mirror = output / item.relative_to(root)
    encoded = mirror.with_suffix(".mp4") if item.suffix.lower() in VIDEO_EXTENSIONS else mirror
    return Source(item, root, encoded, mirror)


def validate_output_folder(path: Path, output: Path) -> None:
    if path.is_dir() and inside(output, path):
        raise InvalidInput(
            f"output folder {output} is inside input folder {path}; "
            "choose an output folder outside it"
        )
    if not path.is_dir() and folded(output) == folded(path.parent):
        raise InvalidInput(f"output folder {output} is the source file's own folder: {path}")


def validate_paths(sources: list[Source], output: Path, roots: set[Path]) -> None:
    claimed: dict[str, Source] = {}
    # Resolve once and test prefixes, so large trees stay linear instead of quadratic.
    trees = {folded(root): root for root in roots}
    originals = {folded(source.path): source.path for source in sources}
    for source in sources:
        for candidate in {source.output, source.no_gain}:
            name = (
                candidate.name if source.next_to_source else candidate.relative_to(output).parts[0]
            )
            if name.casefold() in {
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
    key = str(Path(*folded(candidate)))
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
