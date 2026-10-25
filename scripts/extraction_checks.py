"""Conservative record checks; no claim of semantic verification from tokens."""
import re


def check_extraction(result, supplied_sources):
    """Detect unsupported numbers and invalid source IDs/lines.

    Returns REVIEW when deterministic checks pass. Copying numbers alone cannot
    prove completeness, field association, ordering or arbitrary paraphrases.
    """
    issues = []
    available = {}
    for source in supplied_sources:
        if source["id"] in available:
            available[source["id"]]["text"] += "\n" + source.get("text", "")
        else:
            available[source["id"]] = {**source, "text": source.get("text", "")}
    cited = result.get("sources", [])
    if not supplied_sources or not cited:
        return {"verdict": "REVIEW", "issues": [], "reason": "No supplied source/citation binding"}
    texts = []
    for citation in cited:
        source = available.get(citation.get("id"))
        if not source:
            issues.append("Unknown source ID: " + str(citation.get("id")))
            continue
        text = source.get("text", "")
        labels = set(re.findall(r"\bL\d+\b", text))
        mentioned = re.findall(r"\bL\d+\b", citation.get("locator", ""))
        if source.get("delivery") not in {"supplied_inline", "retrieve_capture", "frozen_dependency_span"} and any(label not in labels for label in mentioned):
            issues.append("Citation references a line absent from the supplied source")
        # A short supporting quote is not the complete evidence assigned to the
        # task. Check against its bound source; the model checks line entailment.
        texts.append(text)
    body = result.get("answer", "") + "\n" + "\n".join(result.get("gaps", []))
    evidence = "\n".join(texts)
    body_without_labels = re.sub(r"(?m)^\s*\d+[.)]\s+", "", re.sub(r"\bL\d+\b", "", body))
    evidence_without_labels = re.sub(r"\bL\d+\b", "", evidence)
    # Sources often attach a unit directly: 24hr, 600ml, 250g.
    numbers = lambda value: set(re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\d.])", value))
    unsupported = numbers(body_without_labels) - numbers(evidence_without_labels)
    if unsupported:
        issues.append("Numbers absent from supplied evidence: " + ", ".join(sorted(unsupported)))
    unit_pattern = r"\b(\d+(?:\.\d+)?)\s*(grams?|kilograms?|g|kg|ml|milliliters?|millilitres?|l|hours?|hrs?|minutes?|mins?|C|°C)\b"
    aliases = {"gram": "g", "kilogram": "kg", "milliliter": "ml", "millilitre": "ml",
               "hr": "hour", "min": "minute"}
    def normalize(pair):
        unit = pair[1].lower().replace("°", "").rstrip("s")
        return pair[0], aliases.get(unit, unit)
    evidence_units = {normalize(pair) for pair in re.findall(unit_pattern, evidence_without_labels, re.I)}
    for pair in re.findall(unit_pattern, body_without_labels, re.I):
        if normalize(pair) not in evidence_units:
            issues.append("Number/unit pair absent from evidence: " + " ".join(pair))
    labels = set(re.findall(r"\bL\d+\b", "\n".join(s.get("text", "") for s in supplied_sources)))
    if any(label not in labels for label in re.findall(r"\bL\d+\b", body)):
        issues.append("Answer or gaps reference a nonexistent source line")
    return {"verdict": "FAIL" if issues else "REVIEW", "issues": issues,
            "reason": "Record checks only; completeness, associations and meaning still require review"}
