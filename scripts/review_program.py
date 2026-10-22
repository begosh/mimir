"""Explicitly activate an evaluated instruction candidate, leaving the original intact."""
import argparse
import json
from pathlib import Path
from evaluate_research import read_candidate
from source_store import identity
from research_program import load_instruction_manifest


def review(candidate_path, evaluation_path, output, *, review_note):
    candidate = read_candidate(candidate_path)
    evaluation = json.loads(Path(evaluation_path).read_text(encoding="utf-8"))
    if evaluation.get("candidate_sha256") != candidate["sha256"]:
        raise ValueError("Evaluation belongs to a different candidate")
    policies = {r["policy"]: r for r in evaluation["results"]}
    baseline, evolved = policies["rlm"], policies["optimized-rlm"]
    if baseline["status"] != "completed" or evolved["status"] != "completed" or evolved["correct"] < baseline["correct"] or evolved["correct"] != evolved["total"]:
        raise ValueError("Held-out correctness gate did not pass")
    if not review_note.strip():
        raise ValueError("Explicit review note is required")
    target = Path(output)
    if target.exists():
        raise ValueError("Reviewed manifest output exists")
    candidate["evaluation"].update(parent_sha256=candidate["sha256"], evaluation_sha256=identity(evaluation),
                                  review_note=review_note,
                                  rollback="Omit program_manifest to use the locked default instructions in a new run")
    candidate["reviewed"] = True
    candidate["sha256"] = identity({k: v for k, v in candidate.items() if k != "sha256"})
    target.write_text(json.dumps(candidate, indent=2), encoding="utf-8")
    load_instruction_manifest(target)
    return {"reviewed_manifest": str(target.resolve()), "sha256": candidate["sha256"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Explicit reviewed manifest activation after held-out evaluation")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--evaluation", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--review-note", required=True, help="Record source entailment, failures and intended scope reviewed by the operator")
    args = parser.parse_args()
    print(json.dumps(review(args.candidate, args.evaluation, args.output, review_note=args.review_note)))
