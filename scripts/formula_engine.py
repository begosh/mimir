"""Deterministic computation and verification for explicit supported formulas."""
import ast
import json
import re
from typing import Any, Dict, List, Optional, Tuple

from backend import SwarmResult

WORD_NUMBERS = {
    "zero": 0.0, "one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0, "five": 5.0,
    "six": 6.0, "seven": 7.0, "eight": 8.0, "nine": 9.0, "ten": 10.0,
    "eleven": 11.0, "twelve": 12.0, "sixteen": 16.0, "twenty": 20.0,
}

UNIT_MULTIPLIERS = {
    "kg": 1000.0, "kilogram": 1000.0, "kilograms": 1000.0,
    "l": 1000.0, "liter": 1000.0, "liters": 1000.0, "litre": 1000.0, "litres": 1000.0,
    "g": 1.0, "gram": 1.0, "grams": 1.0,
    "ml": 1.0, "milliliter": 1.0, "milliliters": 1.0, "millilitre": 1.0, "millilitres": 1.0,
}

NAME_ALIASES = {
    "fresh yeast": "yeast", "instant yeast": "yeast", "dry yeast": "yeast",
    "bread flour": "flour", "tipo 00": "flour", "tipo 0": "flour", "all-purpose flour": "flour",
    "fine sea salt": "salt", "sea salt": "salt", "table salt": "salt",
    "lukewarm water": "water", "cold water": "water", "tap water": "water",
}


def extract_quantities(text: str) -> Dict[str, float]:
    """Extract named quantities and numbers from text."""
    quantities: Dict[str, float] = {}
    if not isinstance(text, str):
        return quantities

    # 1. Pattern: 600 g flour, 390g water, 1.2 kg flour
    p1 = re.findall(
        r"(\d+(?:\.\d+)?)\s*(kg|kilograms?|g|grams?|ml|milliliters?|l|liters?|litres?)?\s*(?:of\s+)?(?:fresh\s+|dry\s+|instant\s+|bread\s+|sea\s+)?([a-zA-Z_]\w*)",
        text, re.I
    )
    for num, unit, name in p1:
        name_clean = NAME_ALIASES.get(name.lower(), name.lower())
        if name_clean in {"minutes", "mins", "hours", "hrs", "c", "celsius", "dough", "balls", "portions"}:
            continue
        val = float(num)
        if unit:
            val *= UNIT_MULTIPLIERS.get(unit.lower(), 1.0)
        quantities[name_clean] = val

    # 2. Pattern: Flour: 600 g, Water: 390 g, Yield: 4
    p2 = re.findall(
        r"([a-zA-Z_]\w*)\s*:\s*(\d+(?:\.\d+)?|[a-zA-Z]+)\s*(kg|g|ml|l|dough\s+balls|balls|portions)?",
        text, re.I
    )
    for name, val, unit in p2:
        name_clean = NAME_ALIASES.get(name.lower(), name.lower())
        if val.isdigit() or re.match(r"^\d+\.\d+$", val):
            num_val = float(val)
            if unit:
                num_val *= UNIT_MULTIPLIERS.get(unit.lower().strip(), 1.0)
            quantities[name_clean] = num_val
        elif val.lower() in WORD_NUMBERS:
            quantities[name_clean] = WORD_NUMBERS[val.lower()]

    # 3. Pattern: four dough balls / 4 balls
    m_yield = re.search(r"(\b\w+\b|\d+)\s+(?:dough\s+)?balls", text, re.I)
    if m_yield:
        raw_val = m_yield.group(1).lower()
        if raw_val in WORD_NUMBERS:
            quantities["yield"] = WORD_NUMBERS[raw_val]
            quantities["base_yield"] = WORD_NUMBERS[raw_val]
        elif raw_val.isdigit():
            quantities["yield"] = float(raw_val)
            quantities["base_yield"] = float(raw_val)

    # 4. Pattern: target batch size / scale for X balls
    m_target = re.search(r"(?:target|scale\s+for|batch\s+size|batch\s+of)\s*(?:of\s+)?(\b\w+\b|\d+)\s*(?:dough\s+)?balls", text, re.I)
    if m_target:
        raw_target = m_target.group(1).lower()
        if raw_target in WORD_NUMBERS:
            quantities["target_yield"] = WORD_NUMBERS[raw_target]
        elif raw_target.isdigit():
            quantities["target_yield"] = float(raw_target)

    return quantities


def safe_eval_expression(expr: str, variables: Dict[str, float]) -> float:
    """Safely evaluate an arithmetic expression against variable bindings using AST."""
    tree = ast.parse(expr.strip(), mode="eval")

    def eval_node(node):
        if isinstance(node, ast.Expression):
            return eval_node(node.body)
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise ValueError(f"Unsupported constant: {node.value}")
        elif isinstance(node, ast.Name):
            name = node.id.lower()
            if name not in variables:
                raise KeyError(f"Variable '{name}' not provided")
            return float(variables[name])
        elif isinstance(node, ast.UnaryOp):
            val = eval_node(node.operand)
            if isinstance(node.op, ast.USub):
                return -val
            elif isinstance(node.op, ast.UAdd):
                return +val
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        elif isinstance(node, ast.BinOp):
            left = eval_node(node.left)
            right = eval_node(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            elif isinstance(node.op, ast.Sub):
                return left - right
            elif isinstance(node.op, ast.Mult):
                return left * right
            elif isinstance(node.op, ast.Div):
                if right == 0:
                    raise ZeroDivisionError("Division by zero in formula")
                return left / right
            elif isinstance(node.op, ast.FloorDiv):
                if right == 0:
                    raise ZeroDivisionError("Division by zero in formula")
                return left // right
            elif isinstance(node.op, ast.Mod):
                return left % right
            elif isinstance(node.op, ast.Pow):
                return left ** right
            raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")
        raise ValueError(f"Forbidden AST node in formula: {type(node).__name__}")

    return eval_node(tree)


def identify_formula(text: str, contract: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Identify a supported formula from the contract or objective text."""
    combined = text
    if contract:
        combined = f"{contract.get('objective', '')} {contract.get('formula', '')} {text}"
    low = combined.lower()

    # 1. Explicit formula in contract
    if contract and contract.get("formula"):
        return {
            "type": "custom_expression",
            "name": "Custom formula",
            "expression": contract["formula"],
            "unit": contract.get("unit", ""),
        }

    # 2. Baker's hydration percentage
    if "hydration" in low:
        # Check if explicit formula given in text, e.g. (water / flour) * 100
        expr_match = re.search(r"\(([a-zA-Z]+)\s*/\s*([a-zA-Z]+)\)\s*\*\s*100", combined)
        expr = expr_match.group(0) if expr_match else "(water / flour) * 100"
        return {
            "type": "hydration",
            "name": "Baker's hydration",
            "expression": expr,
            "unit": "%",
            "required_operands": ["water", "flour"],
        }

    # 3. Baker's percentage for other ingredients
    m_bp = re.search(r"baker'?s?\s+percentage\s*(?:of\s+)?(\b\w+\b)?", low)
    if m_bp:
        ingredient = m_bp.group(1) or "salt"
        return {
            "type": "bakers_percentage",
            "name": f"Baker's percentage ({ingredient})",
            "expression": f"({ingredient} / flour) * 100",
            "unit": "%",
            "required_operands": [ingredient, "flour"],
        }

    # 4. Batch scaling
    if "scale" in low or "scaling" in low:
        return {
            "type": "scale",
            "name": "Batch scaling",
            "expression": "amount * (target_yield / base_yield)",
            "unit": "g",
            "required_operands": ["target_yield", "base_yield"],
        }

    # 5. Total dough weight / Sum
    if "total" in low and ("weight" in low or "dough" in low):
        return {
            "type": "total_weight",
            "name": "Total dough weight",
            "expression": "flour + water + salt + yeast",
            "unit": "g",
            "required_operands": ["flour", "water", "salt", "yeast"],
        }

    # 6. Explicit formula expression in text: e.g. (a / b) * 100 or a * (b / c)
    m_expr = re.search(r"(?:formula|calculate):\s*(\(?\s*[a-zA-Z_]\w*\s*[/+*-]\s*[a-zA-Z_]\w*\s*\)?(?:\s*[*+/^-]\s*[\d.]+)?)", combined)
    if m_expr:
        expr = m_expr.group(1).strip()
        return {
            "type": "custom_expression",
            "name": "Formula calculation",
            "expression": expr,
            "unit": "%" if "* 100" in expr or "*100" in expr else "",
        }

    return None


def can_evaluate_deterministically(node: Any, dep_data: Dict[str, Any]) -> bool:
    """Return True if the node is a calculate task with an identifiable supported formula."""
    contract = node.input_artifacts.get("task_contract", {})
    if contract.get("operation") != "calculate":
        return False
    formula = identify_formula(node.prompt, contract)
    return formula is not None


def execute_deterministic_calculation(node: Any, dep_data: Dict[str, Any]) -> SwarmResult:
    """Execute a calculation task deterministically using exact arithmetic."""
    contract = node.input_artifacts.get("task_contract", {})
    formula = identify_formula(node.prompt, contract)
    if formula is None:
        raise ValueError(f"No supported formula identified for task {node.id}")

    # Gather text from dependency outputs and prompt
    evidence_texts = [node.prompt]
    for dep_id, dep_res in dep_data.items():
        if isinstance(dep_res, dict):
            inner = dep_res.get("result", dep_res) if isinstance(dep_res.get("result"), dict) else dep_res
            evidence_texts.append(str(inner.get("answer", "")))
            for claim in inner.get("claims", []):
                evidence_texts.append(str(claim.get("text", "")))
            for src in inner.get("sources", []):
                evidence_texts.append(str(src.get("support_excerpt", "")))

    full_text = "\n".join(evidence_texts)
    operands = extract_quantities(full_text)

    # Check for required operands
    required = formula.get("required_operands", [])
    missing = [op for op in required if op not in operands]

    if missing:
        data = {
            "answer": f"Cannot compute {formula['name']}; missing required operand(s): {', '.join(missing)}.",
            "sources": [],
            "claims": [],
            "gaps": [f"Missing required operands for {formula['name']}: {', '.join(missing)}"],
        }
        return SwarmResult(node.role, "SUCCESS", data, json.dumps(data), tokens_used=0)

    try:
        val = safe_eval_expression(formula["expression"], operands)
        unit = formula.get("unit", "")
        if unit == "%":
            formatted = f"{val:.1f}%"
        elif unit == "g":
            formatted = f"{val:.1f} g" if val != int(val) else f"{int(val)} g"
        else:
            formatted = f"{val:.2f}" if val != int(val) else f"{int(val)}"

        inputs_summary = ", ".join(f"{k}={operands[k]}" for k in sorted(operands) if k in formula["expression"])
        answer = f"{formula['name']} is {formatted} (formula: {formula['expression']}" + (f" with {inputs_summary})" if inputs_summary else ")")

        data = {
            "answer": answer,
            "sources": [],
            "claims": [
                {
                    "text": f"{formula['name']} is {formatted}.",
                    "source_ids": [],
                    "support_status": "supported",
                    "rationale": f"Deterministic computation of {formula['expression']} = {formatted}",
                }
            ],
            "gaps": [],
        }
        return SwarmResult(node.role, "SUCCESS", data, json.dumps(data), tokens_used=0)
    except Exception as exc:
        data = {
            "answer": f"Calculation error during {formula['name']}: {str(exc)}",
            "sources": [],
            "claims": [],
            "gaps": [f"Calculation error: {str(exc)}"],
        }
        return SwarmResult(node.role, "SUCCESS", data, json.dumps(data), tokens_used=0)


def check_calculation(result: Dict[str, Any], node: Any, dep_data: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministically verify that calculation output matches expected formula evaluation."""
    contract = node.input_artifacts.get("task_contract", {})
    if contract.get("operation") != "calculate":
        return {"verdict": "REVIEW", "issues": [], "reason": "Not a calculate task"}

    formula = identify_formula(node.prompt, contract)
    if formula is None:
        return {"verdict": "REVIEW", "issues": [], "reason": "No registered deterministic formula"}

    evidence_texts = [node.prompt]
    for dep_id, dep_res in dep_data.items():
        if isinstance(dep_res, dict):
            evidence_texts.append(str(dep_res.get("answer", "")))
            for claim in dep_res.get("claims", []):
                evidence_texts.append(str(claim.get("text", "")))
            for src in dep_res.get("sources", []):
                evidence_texts.append(str(src.get("support_excerpt", "")))

    full_text = "\n".join(evidence_texts)
    operands = extract_quantities(full_text)
    required = formula.get("required_operands", [])
    missing = [op for op in required if op not in operands]

    if missing:
        # If operands are missing, the worker must report missing operands in gaps
        has_gap = any(any(m in gap.lower() for m in missing) for gap in result.get("gaps", []))
        if not has_gap and result.get("claims"):
            return {
                "verdict": "FAIL",
                "issues": [f"Calculation claims an unsupported result when required operands are missing: {', '.join(missing)}"],
                "check_type": "deterministic_calculation",
            }
        return {"verdict": "REVIEW", "issues": [], "reason": "Missing operands properly declared in gaps"}

    try:
        expected_val = safe_eval_expression(formula["expression"], operands)
        answer = str(result.get("answer", ""))
        claims_text = " ".join(str(c.get("text", "")) for c in result.get("claims", []))
        combined_text = f"{answer} {claims_text}"

        # Look for numbers in the answer/claims
        found_numbers = [float(n) for n in re.findall(r"\b\d+(?:\.\d+)?\b", combined_text)]
        if not found_numbers:
            return {
                "verdict": "FAIL",
                "issues": ["Calculation answer contains no numeric result"],
                "check_type": "deterministic_calculation",
            }

        # Check if expected_val is present within floating tolerance 0.15
        matches = any(abs(n - expected_val) <= 0.15 for n in found_numbers)
        if not matches:
            return {
                "verdict": "FAIL",
                "issues": [f"Calculated value contradicts deterministic calculation: expected {expected_val:.2f}, found {found_numbers}"],
                "check_type": "deterministic_calculation",
            }
        return {"verdict": "REVIEW", "issues": [], "reason": f"Calculation matches deterministic value {expected_val:.2f}"}
    except Exception as exc:
        return {"verdict": "FAIL", "issues": [f"Deterministic formula check error: {str(exc)}"], "check_type": "deterministic_calculation"}
