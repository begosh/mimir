"""Engine freezes retrieve-worker references; excerpts never create captures."""
from copy import deepcopy
from pathlib import Path
import re

from source_store import SourceStore, identity


def capture_result_evidence(result, *, workspace, allowed_domains=(), frozen=()):
    if not isinstance(result, dict) or not result.get("sources"):
        raise ValueError("Retrieve worker returned no sources to capture")
    snapshots = SourceStore(frozen)
    if len(result["sources"]) > 2:
        raise ValueError("Retrieve capture permits at most two named sources")
    sources, spans, aliases = [], [], {}
    output = deepcopy(result)
    for citation in output["sources"]:
        old_id = citation["id"]
        if old_id in aliases:
            raise ValueError("Retrieve worker source IDs must be unique")
        locator = re.sub(r":L\d+(?:-L?\d+)?$", "", citation["locator"])
        locator = locator.split("#", 1)[0] if locator.startswith("https://") else str((Path(workspace) / locator).resolve())
        matches = [s for s in snapshots.to_list() if s["locator"] == locator]
        if len(matches) > 1:
            raise ValueError("Ambiguous frozen source versions")
        source = matches[0] if matches else SourceStore.capture_reference(
            citation["locator"], workspace=workspace, allowed_domains=allowed_domains)
        excerpt = citation["support_excerpt"]
        if not isinstance(excerpt, str) or not excerpt.strip() or len(excerpt) > 16000:
            raise ValueError("Retrieved evidence requires a nonempty bounded exact excerpt")
        start = source["text"].find(excerpt)
        if start < 0:
            raise ValueError("Worker excerpt is absent from engine-captured source")
        if source["text"].find(excerpt, start + 1) >= 0:
            raise ValueError("Retrieved excerpt is ambiguous; provide a unique exact span")
        span = SourceStore([source]).read_span(source["id"], start, start + len(excerpt))
        span.update(retrieval_type=source["retrieval_type"], status="retrieved")
        aliases[old_id] = source["id"]
        if source not in sources:
            sources.append(source)
        if source["id"] not in snapshots.records:
            snapshots.records[source["id"]] = source
        if span not in spans:
            spans.append(span)
        citation.update(id=source["id"], locator=source["locator"], retrieved_at=source["retrieved_at"],
                        retrieval_type=source["retrieval_type"])
    for claim in output.get("claims", []):
        if any(sid not in aliases for sid in claim["source_ids"]):
            raise ValueError("Retrieve finding refers to an unknown source")
        claim["source_ids"] = [aliases[sid] for sid in claim["source_ids"]]
    return output, sources, spans


def validate_capture_packet(packet):
    if packet.get("hash") != identity({k: packet[k] for k in ("sources", "spans")}):
        raise ValueError("Retrieved evidence packet identity changed")
    store = SourceStore(packet["sources"])
    if not 1 <= len(store.records) <= 2 or not packet["spans"]:
        raise ValueError("Invalid retrieved evidence capture count")
    for source in store.to_list():
        from datetime import datetime
        if datetime.fromisoformat(source["retrieved_at"]).tzinfo is None:
            raise ValueError("Capture timestamp requires a time zone")
        expected_id = "capture_" + identity({"locator": source["locator"], "sha256": source["sha256"]})
        if source["id"] != expected_id:
            raise ValueError("Engine capture source identity changed")
    for span in packet["spans"]:
        expected = store.read_span(span["source_id"], span["start"], span["end"])
        source = store.records[span["source_id"]]
        if (any(span.get(key) != value for key, value in expected.items()) or
                span.get("retrieval_type") != source["retrieval_type"] or span.get("status") != "retrieved"):
            raise ValueError("Retrieved evidence span identity changed")
    return store


async def capture_async(result, **options):
    """Join the owned reader on cancellation before releasing run resources."""
    import asyncio
    task = asyncio.create_task(asyncio.to_thread(capture_result_evidence, result, **options))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if task.done() and not task.cancelled():
            task.exception()
        raise


def inline_spans(packet, delivery):
    validate_capture_packet(packet)
    texts = {s["id"]: s["text"] for s in packet["sources"]}
    return [{"id": s["source_id"], "locator": s["locator"], "retrieved_at": s["retrieved_at"],
             "retrieval_type": s["retrieval_type"], "text": s["text"], "sha256": s["sha256"],
             "span_start": s["start"], "span_end": s["end"],
             "line_start": texts[s["source_id"]][:s["start"]].count("\n") + 1,
             "line_end": texts[s["source_id"]][:s["end"] - 1].count("\n") + 1,
             "status": s["status"], "delivery": delivery}
            for s in packet["spans"]]


def bind_dependency_evidence(node, dependency_results):
    bound = []
    for dep in sorted(node.dependencies):
        for packet in dependency_results[dep].get("frozen_evidence", []):
            for source in inline_spans(packet, "frozen_dependency_span"):
                if source not in bound:
                    bound.append(source)
    if not bound:
        return
    limit = node.input_artifacts.get("task_contract", {}).get("max_input_items", 64)
    if len({s["id"] for s in bound}) > limit:
        raise ValueError("Retrieved evidence exceeds dependent input limit")
    supplied = [s for s in node.input_artifacts.get("supplied_sources", [])
                if s.get("delivery") != "frozen_dependency_span"]
    node.input_artifacts["supplied_sources"] = supplied + bound
