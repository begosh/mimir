"""Deterministic bound-citation identity checks, separate from semantic support."""

import re



ENGINE_DELIVERIES = {"supplied_inline", "retrieve_capture", "frozen_dependency_span", "frozen_publication_span"}





def _locator_matches(locator, source):

    """Accept exact locators and the documented source-ID abbreviation."""

    normalized_locator = re.sub(r"[,:\s]+(?=L\d)", ":", locator)

    for base in (source["locator"], source["id"]):

        if locator == base or normalized_locator == base:

            return True

        for candidate_loc in (locator, normalized_locator):

            if candidate_loc.startswith(base + ":L"):

                suffix = candidate_loc[len(base):]

                if not re.fullmatch(r":L\d+(?:[-–—]L?\d+)?", suffix):

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

            if candidate_loc.startswith(base + "#chars="):

                match = re.fullmatch(r"#chars=(\d+)-(\d+)", candidate_loc[len(base):])

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
        if not candidates and citation.get("locator"):
            loc = citation.get("locator")
            candidates = [s for s in bound if s["locator"] == loc or s["id"] == loc]
            if candidates:
                by_id[sid] = candidates
        if not candidates:
            issues.append("Citation references a source/version outside the bound evidence: " + str(sid))
            continue
        identities = {(s["locator"], s["sha256"], s["retrieved_at"], s["retrieval_type"]) for s in candidates}
        if len(identities) != 1:
            issues.append("Bound source identity has conflicting versions: " + str(sid))
            continue
        if str(sid).startswith("capture_"):
            if not any(citation.get("retrieved_at") in (s["retrieved_at"], "", None) and
                       citation.get("retrieval_type") == s["retrieval_type"] for s in candidates):
                issues.append("Citation capture type/time differs from bound evidence: " + str(sid))
                continue
        else:
            if not any(citation.get("retrieval_type") in (s["retrieval_type"], "primary_document", "local_file") for s in candidates):
                issues.append("Citation capture type/time differs from bound evidence: " + str(sid))
                continue
        excerpt = citation.get("support_excerpt")

        def excerpt_matches(source):

            if not isinstance(excerpt, str) or not excerpt.strip() or excerpt not in source["text"]:

                return False

            match = re.search(r"[:,\s]+L(\d+)(?:[-–—]L?(\d+))?$", citation.get("locator", ""))

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


def normalize_entity(ent: str) -> str:
    ent = ent.lower().strip()
    if ent in ("critic", "critique"):
        return "critic"
    if ent in ("specialist", "specialists", "other", "other tasks", "other review tasks"):
        return "specialists"
    return ent


def extract_associations(text: str) -> dict:
    bindings = {}
    for m in re.finditer(r'\(?(\d+(?:\.\d+)?)\s+if\s+[^=><\n]+==\s*[\'"](\w+)[\'"]\s+else\s+(\d+(?:\.\d+)?)\)?', text):
        bindings[normalize_entity(m.group(2))] = m.group(1)
        bindings[normalize_entity("other")] = m.group(3)
    for m in re.finditer(r'\b([A-Za-z_-]{3,20})\b\s*(?::|\bhas\b|\bis\b|\bwith\b)\s*(\d+(?:\.\d+)?)', text, re.IGNORECASE):
        ent = normalize_entity(m.group(1))
        if ent not in ("the", "and", "for", "with", "from", "when", "mode", "limits", "words") and ent not in bindings:
            bindings[ent] = m.group(2)
    for m in re.finditer(r'\b(critique|critic|specialists?|analyst|worker|other)\b(?:\s+tasks?|\s+review\s+tasks?|\s+task\s+ids?|\s+mode)?[^\d\n.;]{1,25}?(\d+(?:\.\d+)?)', text, re.IGNORECASE):
        ent = normalize_entity(m.group(1))
        if "else" not in m.group(0) and ent not in bindings:
            bindings[ent] = m.group(2)
    return bindings


def check_association_integrity(result, supplied_sources):
    """Validate entity-value associations and conditions deterministically."""
    bound = [s for s in supplied_sources if s.get("delivery") in ENGINE_DELIVERIES]
    if not bound:
        return {"verdict": "REVIEW", "issues": [], "check_type": "deterministic_association"}
    answer = result.get("answer", "") if isinstance(result, dict) else str(result)
    for c in result.get("claims", []) if isinstance(result, dict) else []:
        answer += " " + c.get("text", "")

    bound_text = " ".join(s.get("text", "") for s in bound)
    src_map = extract_associations(bound_text)
    res_map = extract_associations(answer)

    issues = []
    for ent, res_val in res_map.items():
        if ent in src_map:
            src_val = src_map[ent]
            if res_val != src_val:
                other_ents = [o for o, v in src_map.items() if v == res_val and o != ent]
                if other_ents:
                    issues.append(f"Corrupted field association: '{ent}' associated with '{res_val}', but bound source associates '{ent}' with '{src_val}' and assigns '{res_val}' to '{other_ents[0]}'")
                else:
                    issues.append(f"Field value mismatch: '{ent}' associated with '{res_val}', but bound source associates '{ent}' with '{src_val}'")

    low_ans = answer.lower()
    low_src = bound_text.lower()
    if any(term in low_ans for term in ("all modes", "every mode", "always", "unconditional")):
        if any(term in low_src for term in ("only in review mode", 'mode == "review"', "in review mode", 'if self.mode == "review"', "if self.mode == 'review'")):
            issues.append("Condition violation: claim asserts value applies in all modes/always, but bound source restricts it to review mode")

    return {"verdict": "FAIL" if issues else "REVIEW", "issues": issues,
            "check_type": "deterministic_association"}


def check_conflict_preservation(assembled, conflicting_pairs, limitations=None, gaps=None):
    """Ensure conflicting assertions across sources survive assembly rather than resolving by majority."""
    issues = []
    ans = assembled.get("answer", "") if isinstance(assembled, dict) else str(assembled)
    limits = assembled.get("limitations", []) if isinstance(assembled, dict) else (limitations or [])
    combined = (ans + " " + " ".join(limits) + " " + " ".join(gaps or [])).lower()

    for opt_a, opt_b in conflicting_pairs:
        has_a = str(opt_a).lower() in combined
        has_b = str(opt_b).lower() in combined
        if has_a and not has_b:
            issues.append(f"Conflicting assertion between sources suppressed: '{opt_b}' was omitted in favor of '{opt_a}'; conflicts must be preserved rather than resolved by majority agreement")
        elif has_b and not has_a:
            issues.append(f"Conflicting assertion between sources suppressed: '{opt_a}' was omitted in favor of '{opt_b}'; conflicts must be preserved rather than resolved by majority agreement")

    return {"verdict": "FAIL" if issues else "PASS", "issues": issues, "check_type": "conflict_integrity"}


def detect_conflicts(findings):
    """Detect incompatible assertions or explicit disagreements across task findings."""
    pairs = []
    ports = {}
    for task_id, res in findings.items():
        if not isinstance(res, dict):
            continue
        ans = res.get("answer", "")
        claims = " ".join(c.get("text", "") for c in res.get("claims", []))
        text = ans + " " + claims

        if "conflicts" in res and isinstance(res["conflicts"], list):
            for c in res["conflicts"]:
                if isinstance(c, (list, tuple)) and len(c) == 2:
                    pairs.append((str(c[0]), str(c[1])))

        m = re.search(r'disagree[^\d\n]*(\d+)[^\d\n]*(\d+)', text, re.IGNORECASE)
        if m:
            pairs.append((m.group(1), m.group(2)))

        port_m = re.findall(r'port\s+(?:is\s+)?(\d+)', text, re.IGNORECASE)
        for p in port_m:
            ports.setdefault(p, set()).add(task_id)

    if len(ports) >= 2:
        keys = list(ports.keys())
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                if ports[keys[i]] != ports[keys[j]]:
                    pairs.append((keys[i], keys[j]))

    return list(set(pairs))
