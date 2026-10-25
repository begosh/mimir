"""Deterministic bound-citation identity checks, separate from semantic support."""
import re

ENGINE_DELIVERIES = {"supplied_inline", "retrieve_capture", "frozen_dependency_span", "frozen_publication_span"}


def _locator_matches(locator, source):
    """Accept exact locators and the documented source-ID abbreviation."""
    for base in (source["locator"], source["id"]):
        if locator == base:
            return True
        if locator.startswith(base + ":L"):
            suffix = locator[len(base):]
            if not re.fullmatch(r":L\d+(?:-L?\d+)?", suffix):
                continue
            numbers = [int(n) for n in re.findall(r"\d+", suffix)]
            if source.get("line_start") is not None:
                return source["line_start"] <= numbers[0] <= numbers[-1] <= source["line_end"]
            # Labels in bound text are explicit evidence; full file line numbers
            # cannot be established from an excerpt alone and are not guessed.
            labels = set(re.findall(r"\bL\d+\b", source["text"]))
            if source.get("delivery") == "supplied_inline" and not labels:
                return 1 <= numbers[0] <= numbers[-1] <= len(source["text"].splitlines())
            mentioned = re.findall(r"L\d+", suffix)
            return bool(labels) and all(label in labels for label in mentioned)
        if locator.startswith(base + "#chars="):
            match = re.fullmatch(r"#chars=(\d+)-(\d+)", locator[len(base):])
            if match and source.get("span_start") is not None:
                return (int(match[1]), int(match[2])) == (source["span_start"], source["span_end"])
    return False


def check_bound_citations(result, supplied_sources):
    """Prove identity/type/time and exact excerpt membership, never entailment."""
    bound = [s for s in supplied_sources if s.get("delivery") in ENGINE_DELIVERIES]
    if not bound:
        return {"verdict": "REVIEW", "issues": [], "check_type": "structural_provenance"}
    issues = []
    if not isinstance(result, dict) or not isinstance(result.get("sources"), list):
        return {"verdict": "FAIL", "issues": ["Bound evidence requires structured citations"],
                "check_type": "structural_provenance"}
    by_id = {}
    for source in bound:
        if source.get("delivery") == "supplied_inline":
            import hashlib
            if hashlib.sha256(source["text"].encode()).hexdigest() != source["sha256"]:
                issues.append("Bound full source content differs from its version hash: " + source["id"])
        by_id.setdefault(source["id"], []).append(source)
    for citation in result["sources"]:
        sid = citation.get("id")
        candidates = by_id.get(sid, [])
        if not candidates:
            issues.append("Citation references a source/version outside the bound evidence: " + str(sid))
            continue
        identities = {(s["locator"], s["sha256"], s["retrieved_at"], s["retrieval_type"]) for s in candidates}
        if len(identities) != 1:
            issues.append("Bound source identity has conflicting versions: " + str(sid))
            continue
        if not any(citation.get("retrieved_at") == s["retrieved_at"] and
                   citation.get("retrieval_type") == s["retrieval_type"] for s in candidates):
            issues.append("Citation capture type/time differs from bound evidence: " + str(sid))
            continue
        excerpt = citation.get("support_excerpt")
        def excerpt_matches(source):
            if not isinstance(excerpt, str) or not excerpt.strip() or excerpt not in source["text"]:
                return False
            match = re.search(r":L(\d+)(?:-L?(\d+))?$", citation.get("locator", ""))
            if match and (source.get("line_start") is not None or
                          (source.get("delivery") == "supplied_inline" and not re.search(r"\bL\d+\b", source["text"]))):
                start_line = source.get("line_start", 1)
                lines = source["text"].splitlines(keepends=True)
                selected = "".join(lines[int(match[1]) - start_line:int(match[2] or match[1]) - start_line + 1])
                return excerpt in selected
            return True
        if not any(_locator_matches(citation.get("locator", ""), s) and excerpt_matches(s) for s in candidates):
            issues.append("Citation locator/span or exact excerpt differs from bound evidence: " + str(sid))
    for claim in result.get("claims", []):
        if any(sid not in by_id for sid in claim.get("source_ids", [])):
            issues.append("Material claim links to an unbound source/version")
    return {"verdict": "FAIL" if issues else "REVIEW", "issues": issues,
            "check_type": "structural_provenance"}
