"""Own a DSPy execution process and route effects onto the native owner loop."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from backend import SwarmResult
from invocation_broker import BudgetExhausted
from mimir_config import ConfigurationRequired
from owned_process import ProcessOwner, subprocess_options, terminate_owned
from source_store import identity

MAX_FRAME = 4_000_000


async def run_program(request, context, *, optimize=None):
    from research_program import research_python
    broker = context.broker
    if not hasattr(broker.native, "spawn_restricted"):
        raise ConfigurationRequired("DSPy/RLM currently requires a qualified text-only native adapter")
    child = Path(__file__).with_name("worker.py")
    env = {k: v for k, v in os.environ.items() if k.upper() in {
        "SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA",
        "APPDATA", "PYTHONIOENCODING", "DENO_DIR"}}
    env["PYTHONIOENCODING"] = "utf-8"
    env["DSPY_CACHEDIR"] = str(context.run_directory / "dspy-cache")
    process = await asyncio.create_subprocess_exec(
        research_python(), "-u", str(child), stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env=env, limit=MAX_FRAME + 1, **subprocess_options())
    owner = None
    pending = set()
    failure = []
    write_lock = asyncio.Lock()
    seen = set()
    result_data = None
    trace = []
    start_call = len(broker.usage_calls)
    trace_path = context.run_directory / f"{request.task_id}-{start_call + 1}-research-trace.json"
    completed = False
    import time
    timeout = max(.001, broker.deadline - time.time()) if broker.deadline else 1800
    leases = set()
    trace_chars = 0

    async def send(frame):
        data = (json.dumps(frame, ensure_ascii=False, allow_nan=False) + "\n").encode()
        if len(data) > MAX_FRAME:
            raise ConfigurationRequired("DSPy IPC frame exceeds size limit")
        async with write_lock:
            process.stdin.write(data)
            await process.stdin.drain()

    async def effect(frame):
        nonlocal trace_chars
        op = frame["id"]
        try:
            if frame["kind"] == "lm":
                payload = frame["payload"]
                if set(payload) != {"messages", "instructions", "depth", "parent"}:
                    raise ValueError("Invalid normalized native request")
                prompt = "MIMIR DSPY TEXT COMPLETION\n" + json.dumps(
                    {"version": 1, "messages": [m for m in payload["messages"]
                     if m["role"] not in {"system", "developer"}]}, ensure_ascii=False)
                instructions = "\n".join([payload["instructions"] or ""] +
                                         [m["text"] for m in payload["messages"]
                                          if m["role"] in {"system", "developer"}])
                response = await broker.invoke(prompt, role=f"DSPy-{request.task_id}",
                                               depth=payload["depth"], parent=payload["parent"],
                                               restricted=True, model=request.model,
                                               effort=request.effort, json_schema=None, input_data=None,
                                               completion_instructions=instructions)
                if response.status != "SUCCESS":
                    raise ConfigurationRequired("Required native DSPy call failed; no successful research output")
                value = {"text": response.raw_response, "tokens": response.tokens_used or None,
                         "operation_id": response.operation_id}
                await send({"id": op, "ok": True, "value": value})
            elif frame["kind"] == "trace":
                trace_chars += len(json.dumps(frame["payload"]))
                if trace_chars > 8_000_000:
                    raise BudgetExhausted("Research trace size limit exhausted")
                if frame["payload"].get("kind") == "policy_failure":
                    failure.append("policy_failure")
                trace.append(frame["payload"])
                await send({"id": op, "ok": True, "value": None})
            elif frame["kind"] == "interpreter":
                payload = frame["payload"]
                lease = (process.pid, payload["id"])
                if payload["action"] == "open":
                    if lease in broker.interpreters or len(broker.interpreters) >= broker.budget["max_interpreters"] or payload["depth"] > broker.budget["max_depth"]:
                        raise BudgetExhausted("Run interpreter budget exhausted")
                    broker.interpreters.add(lease)
                    leases.add(lease)
                elif payload["action"] == "close" and lease in leases:
                    broker.interpreters.discard(lease)
                    leases.discard(lease)
                else:
                    raise ValueError("Invalid interpreter lease")
                await send({"id": op, "ok": True, "value": None})
            elif frame["kind"] == "source":
                payload = frame["payload"]
                if payload["method"] not in {"list_sources", "read_span", "search_sources"}:
                    raise ValueError("Source operation is outside the capture allowlist")
                value = getattr(context.sources, payload["method"])(**payload["args"])
                trace.append({"kind": "source", **payload, "result_hash": identity(value)})
                await send({"id": op, "ok": True, "value": value})
            else:
                raise ValueError("Unsupported DSPy broker operation")
        except BaseException as exc:
            failure.append(type(exc).__name__)
            if not isinstance(exc, asyncio.CancelledError):
                await send({"id": op, "ok": False, "error": type(exc).__name__})

    async def drain_stderr():
        # Drain bounded chunks; raw library errors can contain private prompts.
        while await process.stderr.read(8192):
            pass

    stderr_task = asyncio.create_task(drain_stderr())
    try:
        # Child waits for initialization, so its descendants cannot predate ownership.
        owner = ProcessOwner(process.pid)
        await send({"kind": "initialize", "request": request.__dict__,
                    "config": context.config, "optimize": optimize})
        async with asyncio.timeout(timeout):
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                if len(line) > MAX_FRAME:
                    raise ConfigurationRequired("DSPy output exceeded frame limit")
                frame = json.loads(line)
                if frame.get("kind") == "result":
                    if result_data is not None:
                        raise ValueError("Duplicate DSPy result")
                    result_data = frame["value"]
                elif frame.get("kind") == "error":
                    raise ConfigurationRequired("DSPy execution failed: " + frame.get("error", "unknown"))
                else:
                    if set(frame) != {"id", "kind", "payload"} or frame["id"] in seen:
                        raise ValueError("Invalid/duplicate DSPy operation")
                    seen.add(frame["id"])
                    task = asyncio.create_task(effect(frame))
                    pending.add(task)
                    def finished(task):
                        pending.discard(task)
                        if not task.cancelled() and task.exception() is not None:
                            failure.append(type(task.exception()).__name__)
                    task.add_done_callback(finished)
            await asyncio.gather(*pending)
            code = await process.wait()
            if code or failure or result_data is None:
                raise ConfigurationRequired("DSPy execution incomplete; required operation failure retained")
            if optimize is None and request.schema:
                import jsonschema
                try:
                    jsonschema.validate(result_data, request.schema)
                except jsonschema.ValidationError as exc:
                    failure.append("schema_invalid")
                    raise ConfigurationRequired("DSPy result schema invalid at " + "/".join(map(str, exc.absolute_path))) from None
                context.sources.validate_citations(result_data)
            completed = True
    except BaseException as exc:
        failure.append(type(exc).__name__)
        raise
    finally:
        async def cleanup():
            for task in list(pending):
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            await terminate_owned(process, owner)
            broker.interpreters.difference_update(leases)
            await stderr_task
        joined = asyncio.create_task(cleanup())
        interrupted = False
        while not joined.done():
            try:
                await asyncio.shield(joined)
            except asyncio.CancelledError:
                interrupted = True
        joined.result()
        context.run_directory.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(json.dumps({"program": context.config["program"],
                                        "state": "completed" if completed and not interrupted else "failed",
                                        "source_digest": context.sources.digest, "events": trace,
                                        "failures": failure,
                                        "attempts": [c for c in broker.usage_calls[start_call:]
                                                     if c["role"] == f"DSPy-{request.task_id}"]},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
        if interrupted:
            raise asyncio.CancelledError
    tokens = sum(c.get("tokens_used") or 0 for c in broker.usage_calls[start_call:]
                 if c["role"] == f"DSPy-{request.task_id}")
    return SwarmResult(request.role, "SUCCESS", result_data,
                       json.dumps(result_data, ensure_ascii=False), tokens_used=tokens), str(trace_path)
