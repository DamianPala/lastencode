"""Run bounded per-source work, reserving space and publishing results on completion."""

import shutil
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue

from lastencode.encoding import encode_source, fail_copy_file
from lastencode.errors import MissingTool
from lastencode.identity import initialize, now
from lastencode.manifest import append, load, protected_paths
from lastencode.processes import Control, use_control
from lastencode.resume import clean_leftovers, manifest_skip, prepare, protected_conflict
from lastencode.trash_gate import trash_original, trash_previous


def free_space(output: Path) -> int:
    return shutil.disk_usage(output).free


@dataclass
class Run:
    output: Path
    jobs: int
    force: bool
    versions: dict[str, str | None]
    trash_originals: bool = False
    trash_targets: set[str] | None = None
    changed: bool = False
    control: Control = field(default_factory=Control)

    def process(
        self, record: dict[str, object], previous: dict[str, object] | None
    ) -> dict[str, object]:
        with use_control(self.control):
            return self.process_source(record, previous)

    def process_source(
        self, record: dict[str, object], previous: dict[str, object] | None
    ) -> dict[str, object]:
        initialize(record)
        record.update(self.versions)
        record["force"] = self.force
        try:
            needs_execution = prepare(record, previous, self.force)
            clean_leftovers(record)
            if needs_execution:
                encode_source(record, jobs=self.jobs)
        except (OSError, ValueError, MissingTool) as error:
            if record["action"] == "copy-file":
                fail_copy_file(record, str(error))
            else:
                record.update(status="failed", reason=str(error))
        record.pop("force", None)
        if record["status"] == "failed":
            record.update(output_size_bytes=None, output_sha256=None)
        record["ended_at"] = now()
        return record

    def quick_skip(self, record: dict[str, object], previous: dict[str, object] | None) -> bool:
        if self.force or previous is None or record["status"] == "failed":
            return False
        if protected_conflict(record, previous):
            return False
        initialize(record)
        record.update(self.versions)
        try:
            if not manifest_skip(record, previous):
                return False
            clean_leftovers(record)
        except OSError:
            return False  # Normal processing reports the per-source error.
        record["ended_at"] = now()
        return True

    def emit(
        self, record: dict[str, object], previous: dict[str, object] | None = None
    ) -> dict[str, object]:
        # Appending a manifest line itself is an intended persistent change.
        self.changed = True
        record["changed"] = self.changed
        try:
            if self.force:
                trash_previous(
                    record,
                    previous,
                    self.output,
                    enabled=self.trash_originals,
                    allowed_paths=self.trash_targets,
                )
            if self.trash_originals:
                trash_original(record, allowed_paths=self.trash_targets)
        finally:
            record["ended_at"] = now()
            append(self.output, record)
        return record

    def records(self, records: list[dict[str, object]]) -> Iterator[dict[str, object]]:
        previous = load(self.output)
        if not self.force:
            protected: dict[str, object] = {"protected_outputs": protected_paths(previous)}
            for record in records:
                protected_conflict(record, protected)
        pending = iter(records)
        running: dict[Future[dict[str, object]], int] = {}
        with ThreadPoolExecutor(max_workers=self.jobs) as pool:
            ordered = iter(records)
            next_record = next(ordered, None)
            buffered: dict[str, dict[str, object]] = {}
            try:
                for result in self.schedule(pool, pending, previous, running):
                    buffered[str(result["source_path"])] = result
                    while next_record is not None and str(next_record["source_path"]) in buffered:
                        yield buffered.pop(str(next_record["source_path"]))
                        next_record = next(ordered, None)
            except BaseException as error:
                # A closed pipe never closes this stream; abandoning it means the consumer failed.
                self.control.cancel()
                if not isinstance(error, GeneratorExit):
                    # Held records are already in the manifest; publish them in plan order.
                    keys = [str(r["source_path"]) for r in records]
                    yield from (buffered.pop(key) for key in keys if key in buffered)
                raise

    def schedule(
        self,
        pool: ThreadPoolExecutor,
        pending: Iterator[dict[str, object]],
        previous: dict[str, dict[str, object]],
        running: dict[Future[dict[str, object]], int],
    ) -> Iterator[dict[str, object]]:
        completed: Queue[Future[dict[str, object]]] = Queue()
        reserved = 0
        stopped: tuple[int, int] | None = None
        exhausted = False
        while not exhausted or running:
            while not exhausted and len(running) < self.jobs:
                record = next(pending, None)
                if record is None:
                    exhausted = True
                    break
                prior = previous.get(str(record["source_path"]))
                needed = 0
                if self.quick_skip(record, prior):
                    future = ready(record)
                else:
                    needed = 2 * int(str(record.get("source_size_bytes") or 0))
                    available = free_space(self.output)
                    if stopped is None and available < reserved + needed:
                        stopped = (reserved + needed, available)
                    if stopped is not None:
                        future = ready(space_failure(record, stopped[0], stopped[1]))
                        needed = 0
                    else:
                        future = pool.submit(self.process, record, prior)
                future.add_done_callback(completed.put)
                running[future] = needed
                reserved += needed
            if running:
                future = completed.get()
                reserved -= running.pop(future)
                result = future.result()
                yield self.emit(result, previous.get(str(result["source_path"])))


def space_failure(record: dict[str, object], needed: int, available: int) -> dict[str, object]:
    initialize(record)
    record.update(
        status="failed",
        action="failure",
        failing_check="Space",
        reason=f"Insufficient output space: need {needed} bytes, available {available} bytes; "
        "no further jobs started",
        space_needed_bytes=needed,
        space_available_bytes=available,
        output_size_bytes=None,
        output_sha256=None,
        ended_at=now(),
    )
    return record


def ready(record: dict[str, object]) -> Future[dict[str, object]]:
    future: Future[dict[str, object]] = Future()
    future.set_result(record)
    return future
