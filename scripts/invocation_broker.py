"""One run-owned admission ledger and native dispatch seam."""
from __future__ import annotations

import asyncio
import json
import math
import os
import time
from pathlib import Path

from backend import BaseSwarmBackend
from mimir_config import ConfigurationRequired
from source_store import identity


class BudgetExhausted(ConfigurationRequired):
    pass


def validate_budget(value=None):
    defaults = dict(max_attempts=64, max_seconds=1800, max_depth=1,
                    max_iters=6, max_subcalls=8, max_interpreters=4,
                    max_output_chars=16000, max_reported_tokens=None)
    if value is not None:
        if not isinstance(value, dict) or set(value) - set(defaults):
            raise ValueError("Unknown research budget fields")
        defaults.update(value)
    for name, val in defaults.items():
        if name == "max_reported_tokens" and val is None:
            continue
        if name == "max_seconds":
            valid = type(val) in (int, float) and math.isfinite(val) and 1 <= val <= 86400
        else:
            valid = type(val) is int and (0 if name == "max_depth" else 1) <= val <= 10_000_000
        if not valid:
            raise ValueError(f"Invalid research budget {name}")
    if defaults["max_depth"] > 4 or defaults["max_interpreters"] > 16:
        raise ValueError("Recursive depth is at most 4; interpreters at most 16")
    return defaults


class InvocationBroker(BaseSwarmBackend):
    """Backend-compatible adapter; resource ownership remains with its native adapter."""
    def __init__(self, native, *, max_context_chars=120000, calls=(), budget=None,
                 journal=None, policy=None, recover=False):
        self.native = native
        self.default_model = native.default_model
        self.default_effort = native.default_effort
        self.max_concurrency = native.max_concurrency
        self.usage_calls = list(calls)
        self.max_context_chars = max_context_chars
        self.budget = validate_budget(budget) if budget is not None else None
        self.journal = Path(journal) if journal else None
        self.policy = policy or {}
        began = time.time()
        if recover and self.journal and self.journal.is_file():
            ledger = {c["operation_id"]: c for c in self.usage_calls}
            lines = self.journal.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    if index != len(lines) - 1:
                        raise ConfigurationRequired("Operation journal is corrupt") from None
                    # A crash can tear the final write; preserve the valid prefix.
                    self.journal.write_text("\n".join(lines[:index]) + "\n", encoding="utf-8")
                    break
                if item.get("kind") == "budget_started":
                    began = item["time"]
                elif "operation_id" in item:
                    ledger[item["operation_id"]] = item
            self.usage_calls = sorted(ledger.values(), key=lambda c: int(c["operation_id"].split("-")[-1]))
            for entry in self.usage_calls:
                if entry["status"] == "inflight":
                    entry["status"] = "interrupted"
        elif self.journal and self.journal.exists():
            self.journal.rename(self.journal.with_name(self.journal.name + f".{time.time_ns()}.previous"))
        self.deadline = began + self.budget["max_seconds"] if self.budget else None
        if self.budget:
            self.event({"kind": "budget_started", "time": began})
        self.attempts = len(self.usage_calls)
        self.reserve_for_review = 0
        self.required_failures = []
        self._semaphore = asyncio.Semaphore(self.max_concurrency)
        self.interpreters = set()

    def __getattr__(self, name):
        return getattr(self.native, name)

    @property
    def execution_identity(self):
        base = getattr(self.native, "execution_identity", None)
        return {"native": base, "program": self.policy} if self.policy else base

    def event(self, item):
        if self.journal:
            self.journal.parent.mkdir(parents=True, exist_ok=True)
            with self.journal.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())

    async def invoke(self, prompt, *, role="Micro-Worker", depth=0, parent=None,
                     restricted=False, **options):
        serialized = json.dumps(options.get("input_data"), ensure_ascii=False) if options.get("input_data") is not None else ""
        input_chars = len(prompt) + len(serialized) + len(options.get("completion_instructions") or "")
        if input_chars > self.max_context_chars:
            raise ConfigurationRequired("Worker context exceeds --max-context-chars; evidence was retained without truncation.")
        if options.get("model") not in (None, self.default_model) or options.get("effort") not in (None, self.default_effort):
            raise ConfigurationRequired("Native model and effort are fixed for this run")
        async with self._semaphore:
            if self.budget:
                protected = role in {"Red-Team-Critic", "GEPA-Evolver"}
                available = self.budget["max_attempts"] - (0 if protected else self.reserve_for_review)
                if self.attempts >= available or time.time() >= self.deadline or depth > self.budget["max_depth"]:
                    raise BudgetExhausted("Research budget exhausted; completed evidence retained without successful publication.")
                limit = self.budget["max_reported_tokens"]
                if limit and sum(c.get("tokens_used") or 0 for c in self.usage_calls) >= limit:
                    raise BudgetExhausted("Reported token threshold reached; native turn usage can overshoot this threshold.")
            if restricted and not hasattr(self.native, "spawn_restricted"):
                raise ConfigurationRequired("Selected native adapter cannot enforce text-only research calls")
            self.attempts += 1
            op = f"attempt-{self.attempts}"
            started = time.monotonic()
            entry = {"operation_id": op, "parent": parent, "depth": depth,
                     "role": role, "input_chars": input_chars,
                     "input_hash": identity({"prompt": prompt, "options": options}),
                     "status": "inflight", "tokens_used": None}
            self.usage_calls.append(entry)
            self.event(dict(entry))
            result = None
            try:
                dispatch = self.native.spawn_restricted if restricted else self.native.spawn
                if self.deadline:
                    async with asyncio.timeout(max(.001, self.deadline - time.time())):
                        result = await dispatch(prompt=prompt, role=role, **options)
                else:
                    result = await dispatch(prompt=prompt, role=role, **options)
                entry.update(status=result.status, tokens_used=result.tokens_used or None,
                             output_hash=identity(result.raw_response))
                result.operation_id = op
                if result.status != "SUCCESS":
                    self.required_failures.append(op)
                if self.budget and protected:
                    self.reserve_for_review = max(0, self.reserve_for_review - 1)
                return result
            except BaseException:
                entry["status"] = "interrupted"
                self.required_failures.append(op)
                raise
            finally:
                entry["duration_seconds"] = round(time.monotonic() - started, 3)
                self.event(dict(entry))

    async def spawn(self, prompt, role="Micro-Worker", **options):
        return await self.invoke(prompt, role=role, **options)

    async def aclose(self):
        await self.native.aclose()

    async def check_cli(self):
        return await self.native.check_cli()
