"""Durable run ownership and lifecycle shared by local tool callers.

A manager owns only its own tasks. OS locks prevent two local hosts executing
one run simultaneously; reading status/results requires no lock ownership.
"""
from __future__ import annotations
import asyncio
import json
import math
import os
import re
import time
import uuid
from contextlib import nullcontext
from pathlib import Path
from typing import Callable
from engine import run_mimir, _write_artifact
from backend import WorkerFailure, worker_diagnostic
from mimir_config import ConfigurationRequired

_RUN_ID = re.compile(r"[a-f0-9]{32}\Z")
_ACTIVE = {"queued", "running", "cancelling"}


from run_locks import RunBusyError, ownership as _ownership


class RunManager:
    """Start/resume a phase, read progress, cancel owned work, retrieve artifacts."""
    def __init__(self, root: Path, runner: Callable = run_mimir, max_active: int = 4):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.runner = runner
        self.max_active = max_active
        self._tasks: dict[str, asyncio.Task] = {}
        self._closed = False

    def _directory(self, run_id: str) -> Path:
        if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
            raise ValueError("Invalid run ID.")
        directory = self.root / run_id
        if directory.resolve() != directory or directory.is_symlink():
            raise ValueError("Run directory must not redirect outside its owned location.")
        return directory

    def _read(self, run_id: str) -> dict:
        target = self._directory(run_id) / "run.json"
        if target.is_symlink():
            raise ValueError("Run metadata must not be a link.")
        try:
            value = json.loads(target.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ValueError("Unknown run ID.") from None
        if value.get("run_id") != run_id:
            raise ValueError("Invalid persisted run identity.")
        return value

    def _save(self, record: dict):
        record["updated_at"] = time.time()
        _write_artifact(self._directory(record["run_id"]) / "run.json",
                        json.dumps(record, ensure_ascii=False, indent=2))

    def _reconcile_events(self, record: dict):
        """Repair a crashed tail and reconcile journal-before-metadata commits."""
        path = self._directory(record["run_id"]) / "events.jsonl"
        if path.is_symlink():
            raise ValueError("Event journal must not be a link.")
        if not path.exists():
            return
        last = 0
        latest = None
        valid_end = 0
        with path.open("rb+") as stream:
            while True:
                line = stream.readline()
                if not line:
                    break
                try:
                    item = json.loads(line)
                    sequence = item["sequence"]
                    if type(sequence) is not int or sequence <= last or not line.endswith(b"\n"):
                        break
                except (ValueError, KeyError, TypeError):
                    break
                last = sequence
                latest = item
                valid_end = stream.tell()
            stream.truncate(valid_end)
        # Reserve every committed metadata sequence even if its append tore.
        record["sequence"] = max(record["sequence"], last)
        if latest is not None:
            record["latest_event"] = latest

    def _recover(self, run_id: str, *, repair: bool = False) -> dict:
        """Observe interruption without mutating state on status/result reads."""
        record = self._read(run_id)
        if record["status"] in _ACTIVE and run_id not in self._tasks:
            try:
                lock_path = self._directory(run_id) / "owner.lock"
                # Every admitted run creates its lease before metadata. A
                # missing lease is orphaned metadata; observing it must not
                # create a file as a side effect of a read-only status call.
                lease = _ownership(lock_path) if repair or lock_path.exists() else nullcontext()
                with lease:
                    # Re-read under lease: another process may just have finished.
                    record = self._read(run_id)
                    if repair:
                        self._reconcile_events(record)
                    if record["status"] in _ACTIVE:
                        record.update(status="interrupted", error="Previous owner exited before phase completion.")
                        if repair:
                            self._save(record)
            except RunBusyError:
                pass
        return record

    def _validate_resume(self, directory: Path, record: dict, phase: str):
        checkpoint_path = directory / "checkpoint.json"
        if checkpoint_path.is_symlink() or checkpoint_path.resolve() != checkpoint_path:
            raise ValueError("Checkpoint must remain within its owned run directory.")
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        allowed = {"planned", "executing"} if phase == "execute" else {"executed"}
        if phase == "synthesize" and record["status"] in {"failed", "interrupted", "cancelled"}:
            # The engine verifies publication identity and avoids repeated model
            # calls/learning writes before completing this cleanup-only retry.
            allowed.add("synthesized")
        if checkpoint.get("phase") not in allowed:
            choices = ", ".join(sorted(allowed))
            raise ValueError(f"{phase} requires a {choices} checkpoint.")

    async def start(self, *, goal: str | None = None, backend: str | None = None,
                    model: str | None = None, effort: str | None = None,
                    phase: str = "plan", run_id: str | None = None,
                    worker_transport: str | None = None, worker_timeout: float | None = None,
                    max_concurrency: int | None = None, skip_web: bool = False,
                    search_query: str | None = None, enable_jev: bool | None = None,
                    mode: str | None = None, max_tasks: int | None = None,
                    memory_mode: str | None = None, memory_path: str | None = None,
                    max_context_chars: int | None = None,
                    research_program: str | None = None, research_budget: dict | None = None,
                    source_manifest: str | None = None, program_manifest: str | None = None) -> dict:
        if self._closed:
            raise RuntimeError("Run manager is closed.")
        if research_program not in {None, "native", "dspy", "rlm"}:
            raise ValueError("Research program must be native, dspy or rlm")
        if research_budget is not None:
            from invocation_broker import validate_budget
            validate_budget(research_budget)
        if phase not in {"plan", "execute", "synthesize"}:
            raise ValueError("Choose plan, execute or synthesize.")
        if sum(not task.done() for task in self._tasks.values()) >= self.max_active:
            raise RunBusyError("Too many active phases; wait for completion.")
        if worker_transport not in {None, "native", "cli"}:
            raise ValueError("Worker transport must be native or cli.")
        if worker_timeout is not None and (not math.isfinite(worker_timeout) or worker_timeout <= 0 or worker_timeout > 3600):
            raise ValueError("Worker timeout must be positive and at most 3600 seconds.")
        if max_concurrency is not None and (type(max_concurrency) is not int or not 1 <= max_concurrency <= 32):
            raise ValueError("Concurrency must be an integer from 1 to 32.")
        if mode not in {None, "single", "review", "swarm"}:
            raise ValueError("Mode must be single, review or swarm.")
        if max_tasks is not None and (type(max_tasks) is not int or not 1 <= max_tasks <= 16):
            raise ValueError("Task limit must be an integer from 1 to 16.")
        if memory_mode not in {None, "off", "read", "write"}:
            raise ValueError("Memory mode must be off, read or write.")
        if memory_path is not None and (not isinstance(memory_path, str) or not memory_path.strip()):
            raise ValueError("Memory path must be nonempty text.")
        if max_context_chars is not None and (type(max_context_chars) is not int or not 1000 <= max_context_chars <= 2_000_000):
            raise ValueError("Context character limit must be an integer from 1000 to 2000000.")
        if enable_jev is not None and type(enable_jev) is not bool:
            raise ValueError("JEV selection must be a boolean.")
        if run_id is None:
            if phase != "plan" or not isinstance(goal, str) or not goal.strip():
                raise ValueError("A new run requires a nonempty goal and planning phase.")
            run_id = uuid.uuid4().hex
            directory = self._directory(run_id)
            directory.mkdir()
            record = {"version": 1, "run_id": run_id, "phase": phase, "status": "queued",
                      "created_at": time.time(), "sequence": 0, "invocation": 0,
                      "completed_phase": None, "error": None}
        else:
            record = self._recover(run_id)
            if record["status"] in _ACTIVE:
                raise RunBusyError("Run already has an active phase.")
            if phase == "plan":
                raise ValueError("Replanning requires a new run ID; existing evidence is preserved.")
            directory = self._directory(run_id)
            self._validate_resume(directory, record, phase)
        checkpoint_path = directory / "checkpoint.json"
        if checkpoint_path.is_symlink() or checkpoint_path.resolve() != checkpoint_path:
            raise ValueError("Checkpoint must remain within its owned run directory.")
        lease = _ownership(directory / "owner.lock")
        lease.__enter__()
        try:
            if record["invocation"]:
                # Admission must be rechecked under ownership, not against a
                # snapshot another host can replace while we acquire its lease.
                record = self._read(run_id)
                if record["status"] in _ACTIVE:
                    record.update(status="interrupted", error="Previous owner exited before phase completion.")
                self._validate_resume(directory, record, phase)
            self._reconcile_events(record)
            record.update(phase=phase, status="queued", error=None, error_type=None,
                          invocation=record["invocation"] + 1)
            self._save(record)
            options = dict(goal=goal, backend=backend, model=model, effort=effort,
                           phase=phase, worker_transport=worker_transport, worker_timeout=worker_timeout,
                           max_concurrency=max_concurrency, skip_web=skip_web,
                           search_query=search_query, enable_jev=enable_jev,
                           mode=mode, max_tasks=max_tasks, memory_mode=memory_mode,
                           memory_path=memory_path, max_context_chars=max_context_chars,
                           research_program=research_program, research_budget=research_budget,
                           source_manifest=source_manifest, program_manifest=program_manifest,
                           state_file=str(directory / "checkpoint.json"),
                           output_path=str(directory / "report.md"), progress_format="events")
            task = asyncio.create_task(self._execute(record, options, lease))
            self._tasks[run_id] = task
        except BaseException:
            lease.__exit__(None, None, None)
            raise
        return {"run_id": run_id, "phase": phase, "status": "queued"}

    async def _execute(self, record: dict, options: dict, lease):
        run_id = record["run_id"]
        def event_sink(event):
            record["sequence"] += 1
            item = {**event, "phase_sequence": event["sequence"],
                    "sequence": record["sequence"], "invocation": record["invocation"],
                    "phase_invocation": record["phase"]}
            target = self._directory(run_id) / "events.jsonl"
            if target.is_symlink():
                raise ValueError("Event journal must not be a link.")
            with target.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(item, ensure_ascii=False) + "\n")
                stream.flush()
            record["latest_event"] = item
            # Cancellation is durable until the worker lifecycle actually closes.
            if self._read(run_id).get("status") == "cancelling":
                record["status"] = "cancelling"
            self._save(record)
        try:
            record["status"] = "running"
            self._save(record)
            await self.runner(**options, event_sink=event_sink)
            expected_event = {"plan": "plan_completed", "execute": "execute_completed", "synthesize": "run_completed"}[record["phase"]]
            completion = record.get("latest_event", {})
            if (completion.get("event") != expected_event
                    or completion.get("invocation") != record["invocation"]
                    or completion.get("phase_invocation") != record["phase"]):
                raise RuntimeError("Engine exited without the required phase completion event.")
            record.update(status="completed", completed_phase=record["phase"])
        except asyncio.CancelledError:
            record.update(status="cancelled", error="Phase cancelled; completed checkpoints are retained.")
        except Exception as exc:
            # Typed worker failures preserve actionable templates. Other error
            # messages pass through the same classifier; transcripts never do.
            message = worker_diagnostic("Mimir", str(exc), error=exc)
            latest = record.get("latest_event", {})
            if (isinstance(exc, ConfigurationRequired)
                    and latest.get("event") == "configuration_required"
                    and latest.get("invocation") == record["invocation"]
                    and latest.get("phase_invocation") == record["phase"]
                    and isinstance(latest.get("message"), str)):
                # This event is emitted by owned configuration validation, not
                # an adapter transcript. Keep its precise corrective action.
                message = latest["message"]
            if latest.get("event") == "run_failed" and latest.get("message") == "Worker cleanup failed; verify the local runtime before retrying.":
                message = latest["message"]
            record.update(status="failed", error=message, error_type=type(exc).__name__)
        finally:
            try:
                self._save(record)
            finally:
                lease.__exit__(None, None, None)
                self._tasks.pop(run_id, None)

    def status(self, run_id: str, after_sequence: int = 0, limit: int = 50) -> dict:
        if type(after_sequence) is not int or after_sequence < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Use a nonnegative cursor and event limit from 1 to 100.")
        record = self._recover(run_id)
        events = []
        journal = self._directory(run_id) / "events.jsonl"
        if journal.is_symlink():
            raise ValueError("Event journal must not be a link.")
        if journal.exists():
            with journal.open(encoding="utf-8") as stream:
                for line in stream:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # A crashed final append is not a completed event.
                    if event["sequence"] > after_sequence:
                        events.append(event)
                        if len(events) == limit:
                            break
        recoverable = []
        checkpoint_path = self._directory(run_id) / "checkpoint.json"
        if record["status"] not in _ACTIVE and checkpoint_path.is_file() and not checkpoint_path.is_symlink():
            try:
                checkpoint_phase = json.loads(checkpoint_path.read_text(encoding="utf-8")).get("phase")
            except (ValueError, OSError):
                checkpoint_phase = None
            if checkpoint_phase in {"planned", "executing"}:
                recoverable = ["execute"]
            elif checkpoint_phase == "executed" or (checkpoint_phase == "synthesized" and record["status"] != "completed"):
                recoverable = ["synthesize"]
        return {**record, "events": events, "recoverable_phases": recoverable,
                "next_sequence": events[-1]["sequence"] if events else after_sequence,
                "has_more": bool(events and events[-1]["sequence"] < record["sequence"])}

    async def progress(self, run_id: str, after_sequence: int = 0, limit: int = 50,
                       *, wait_seconds: float = 20, include_events: bool = False) -> dict:
        """Wait boundedly for meaningful progress and return a compact chat view.

        Waiting releases the event loop and never mutates run state. Heartbeats
        advance the cursor but do not trigger another visible progress update.
        """
        from progress import present_progress
        if not isinstance(wait_seconds, (int, float)) or isinstance(wait_seconds, bool) or not math.isfinite(wait_seconds) or not 0 <= wait_seconds <= 25:
            raise ValueError("Progress wait must be between 0 and 25 seconds.")
        deadline = asyncio.get_running_loop().time() + wait_seconds
        while True:
            record = self.status(run_id, after_sequence, limit)
            view = present_progress(record, record["events"], include_events=include_events)
            remaining = deadline - asyncio.get_running_loop().time()
            if (record["status"] not in _ACTIVE or view["updates"] or record["has_more"]
                    or remaining <= 0 or include_events and record["events"]):
                return view
            await asyncio.sleep(min(0.25, remaining))

    async def cancel(self, run_id: str) -> dict:
        record = self._recover(run_id)
        task = self._tasks.get(run_id)
        if task is None:
            if record["status"] in _ACTIVE:
                raise RunBusyError("Cancellation must be sent to the host owning this phase.")
            return {"run_id": run_id, "status": record["status"]}
        # Let queued task enter its try/finally before cancelling it.
        await asyncio.sleep(0)
        if not task.done():
            record = self._read(run_id)
            record["status"] = "cancelling"
            self._save(record)
            if task.cancelling() == 0:
                task.cancel()
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
            task.result()
        return {"run_id": run_id, "status": self._read(run_id)["status"]}

    def result(self, run_id: str, artifact: str = "report", offset: int = 0, limit: int = 32000) -> dict:
        record = self._recover(run_id)
        if record["status"] != "completed" or record.get("completed_phase") != "synthesize":
            raise ValueError("A final result requires successful synthesis and cleanup.")
        if artifact not in {"report", "sidecar"}:
            raise ValueError("Artifact must be report or sidecar.")
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 32000:
            raise ValueError("Use a nonnegative character offset and limit up to 32000.")
        path = self._directory(run_id) / ("report.md" if artifact == "report" else "report.json")
        if path.is_symlink() or path.resolve().parent != self._directory(run_id):
            raise ValueError("Artifact must remain within its owned run directory.")
        with path.open(encoding="utf-8") as stream:
            remaining = offset
            while remaining:
                chunk = stream.read(min(remaining, 32000))
                if not chunk:
                    break
                remaining -= len(chunk)
            content = stream.read(limit)
            has_more = bool(stream.read(1))
        return {"run_id": run_id, "artifact": artifact, "path": str(path), "content": content,
                "offset": offset, "next_offset": offset + len(content), "has_more": has_more}

    async def aclose(self):
        self._closed = True
        # Allow all freshly queued tasks to enter their owned lifecycle.
        await asyncio.sleep(0)
        tasks = list(self._tasks.values())
        for task in tasks:
            if task.cancelling() == 0:
                task.cancel()
        joined = asyncio.gather(*tasks, return_exceptions=True)
        while not joined.done():
            try:
                await asyncio.shield(joined)
            except asyncio.CancelledError:
                continue
        joined.result()
