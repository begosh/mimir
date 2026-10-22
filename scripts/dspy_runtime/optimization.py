"""Dataset-scored upstream GEPA instruction optimization; no automatic promotion."""
from __future__ import annotations

import json


def optimize(job, lm, channel, factory, budget):
    import dspy
    from source_store import identity
    import logging
    class Diagnostics(logging.Handler):
        def emit(self, record):
            message = record.getMessage()
            for marker in ("No valid predictions", "No valid reflective examples", "Exception building reflective dataset",
                           "reflection failed", "All subsample scores perfect", "No trajectories"):
                if marker.lower() in message.lower():
                    channel.call("trace", {"kind": "gepa_diagnostic", "reason": marker})
    handler = Diagnostics()
    logging.getLogger("dspy").addHandler(handler)
    logging.getLogger("dspy").setLevel(logging.INFO)
    train, dev = job["train"], job["dev"]
    def examples(rows):
        return [dspy.Example(objective=r["objective"], evidence=r["evidence"],
                             expected=r["expected"]).with_inputs("objective", "evidence") for r in rows]
    from dspy_runtime.programs import build_student, instruction_map
    student = build_student(job["program"], lm, factory, budget)
    original = instruction_map(student, job["program"])
    def metric(example, prediction, trace=None, pred_name=None, pred_trace=None):
        if trace and pred_name is None:
            channel.call("trace", {"kind": "gepa_predictor_trace", "matches": [
                {"name": name, "count": sum(t[0].signature.equals(p.signature) for t in trace)}
                for name, p in student.named_predictors()]})
        try:
            result = json.loads(prediction.result_json)
            correct = result.get("answer") == example.expected
        except (ValueError, AttributeError):
            correct = False
        return dspy.Prediction(score=float(correct),
                               feedback="Exact answer matches." if correct else
                               "Answer did not match the frozen expected result. Return valid JSON and reason only from evidence.")
    from dspy.teleprompt.gepa.instruction_proposal import InstructionProposer
    builtin = InstructionProposer(adapter=dspy.ChatAdapter())
    proposals = []
    def proposer(**kwargs):
        proposed = builtin(**kwargs)
        entry = {"kind": "instruction_proposal", "parent_sha256": identity(kwargs["candidate"]),
                 "components": kwargs["components_to_update"], "instructions": proposed,
                 "sha256": identity(proposed)}
        proposals.append(entry)
        channel.call("trace", entry)
        return proposed
    optimizer = dspy.GEPA(metric=metric, max_metric_calls=job["max_metric_calls"],
                         instruction_proposer=proposer,
                         reflection_lm=lm, use_merge=False, track_stats=True,
                         num_threads=1, skip_perfect_score=False, reflection_minibatch_size=1,
                         component_selector="all")
    compiled = optimizer.compile(student, trainset=examples(train), valset=examples(dev))
    if channel.failed:
        raise RuntimeError("Required optimization operation failed")
    candidate = {"version": 1, "program": job["program"],
                 "instructions": instruction_map(compiled, job["program"]),
                 "evaluation": {"train_digest": identity(train), "dev_digest": identity(dev),
                                "metric": "exact-answer-fixture-v1", "max_metric_calls": job["max_metric_calls"],
                                "original_instructions": original,
                                "proposals": proposals,
                                "stats": {"scores": compiled.detailed_results.val_aggregate_scores,
                                          "parents": compiled.detailed_results.parents,
                                          "best_idx": compiled.detailed_results.best_idx,
                                          "metric_calls": compiled.detailed_results.total_metric_calls,
                                          "candidate_count": len(compiled.detailed_results.candidates)},
                                "scope": "Engineering fixture correctness; human entailment review and held-out validation required."},
                 "reviewed": False}
    return {**candidate, "sha256": identity(candidate)}
