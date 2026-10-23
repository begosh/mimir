"""Bind explicitly named frozen evidence before atomic execution."""
import re
from mimir_config import ConfigurationRequired
from source_store import SourceStore


def bind_captured_sources(node, config):
    records = SourceStore(config.get("sources", [])).to_list()
    if not records:
        return
    inputs = node.input_artifacts["task_contract"]["inputs"]
    selected = [r for r in records if any(re.search(
        r"(?<![\w])" + re.escape(r["id"]) + r"(?![\w])", value) for value in inputs)]
    if len(selected) > node.input_artifacts["task_contract"].get("max_input_items", 2):
        raise ConfigurationRequired("Captured sources exceed atomic input limit")
    if not selected:
        return  # Inputs may instead be supplied by task dependencies.
    if any(len(r["text"]) > 16000 for r in selected):
        raise ConfigurationRequired("Captured source exceeds atomic inline limit; supply a bounded excerpt")
    existing = node.input_artifacts.get("supplied_sources", [])
    bound = [{**r, "status": config.get("source_statuses", {}).get(r["id"],
             "user_supplied" if r["retrieval_type"] == "local_file" else "retrieved"),
             "delivery": "supplied_inline"} for r in selected]
    for source in bound:
        old = next((s for s in existing if s["id"] == source["id"]), None)
        if old and old != source:
            raise ConfigurationRequired("Captured source binding conflicts with supplied evidence")
        if not old:
            existing.append(source)
    node.input_artifacts["supplied_sources"] = existing
