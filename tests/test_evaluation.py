"""Evaluation accounting distinguishes record presence from factual quality."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import evaluate


class EvaluationAccounting(unittest.IsolatedAsyncioTestCase):
    async def test_failed_runs_and_unknown_usage_are_retained_without_quality_credit(self):
        calls = []
        async def runner(**options):
            calls.append(options["mode"])
            if options["mode"] == "review":
                raise TimeoutError("fixture timeout")
            target = Path(options["output_path"]).with_suffix(".json")
            target.write_text(json.dumps({"hardened_solution": "pin 0.163.0", "usage": {"model_calls": 1,"known_tokens": 0,"usage_complete": False},
                "research": {"coverage": "unknown", "sources": [{"locator":"file:3"}], "claims": [], "gaps": []}}),encoding="utf-8")
        with tempfile.TemporaryDirectory() as temp, patch.object(evaluate,"run_mimir",runner):
            summary = await evaluate.evaluate([{"id":"case","goal":"read file","required_locators":["file:3"],"required_answer_markers":["0.163.0"]}],
                Path(temp)/"new",backend="codex",model="fixture",effort="low",modes=["single","review"],repeats=2,worker_timeout=1)
            self.assertEqual(calls,["single","review","review","single"])
            self.assertEqual(sum(r["status"]=="failed" for r in summary["runs"]),2)
            row=next(r for r in summary["runs"] if r["status"]=="completed")
            self.assertEqual(row["metrics"]["required_locator_hits"],1)
            self.assertEqual(row["metrics"]["citation_entailment"],"requires independent review")
            self.assertFalse(row["usage"]["usage_complete"])


if __name__ == "__main__":unittest.main()
