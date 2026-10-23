"""Model-facing evidence views; internal identities remain in engine records."""
import re
from copy import deepcopy

INTERNAL = {"result_hash", "prompt_hash", "input_fingerprint", "policy", "input_hash",
            "result_check_hash", "result_attempts", "evidence_hash"}


def model_view(value, sources=()):
    aliases = {s["locator"]: s["id"] for s in sources if s.get("id") and
               isinstance(s.get("locator"), str) and re.match(r"^(?:[A-Za-z]:[\\/]|/)", s["locator"])}
    def clean(item):
        if isinstance(item, str):
            for path, alias in sorted(aliases.items(), key=lambda p: -len(p[0])):
                item = item.replace(path, alias)
            return item
        if isinstance(item, list):
            return [clean(v) for v in item]
        if isinstance(item, dict):
            return {k: clean(v) for k, v in item.items() if k not in INTERNAL}
        return item
    return clean(value)


def compact_checker_context(context):
    """Store each evidence text once; bind source references to each candidate."""
    context = deepcopy(context)
    registry = []
    alias_sources = []
    def register(source):
        # Equality of complete records preserves differing statuses/texts.
        alias_sources.append(source)
        source = model_view(source, [source])
        if source not in registry:
            registry.append(source)
        return {"ref": f"source_{registry.index(source)+1}", "id": source.get("id"), "sha256": source.get("sha256")}
    shared = context.pop("supplied_sources", [])
    shared_refs = [register(s) for s in shared]
    for candidate in context.get("candidates", []):
        sources = candidate.pop("supplied_sources", [])
        candidate["source_refs"] = [register(s) for s in sources] or shared_refs
        candidate["result"] = model_view(candidate.get("result", {}), [*shared, *sources])
        # Full source texts already exist in the registry. Retain source IDs and
        # locators, but not duplicate supporting excerpts when text is supplied.
        if candidate["source_refs"]:
            for source in candidate["result"].get("sources", []):
                source.pop("support_excerpt", None)
        candidate["dependency_results"] = model_view(candidate.get("dependency_results", {}), [*shared, *sources])
    if registry:
        context["source_registry"] = [{"ref": f"source_{i}", **s} for i, s in enumerate(registry, 1)]
    return model_view(context, alias_sources)
