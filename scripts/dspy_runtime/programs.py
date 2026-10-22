"""Typed students shared by GEPA training and sealed fixture evaluation."""
def build_student(kind, lm, factory, budget):
    import dspy
    if kind == "dspy":
        return dspy.Predict("objective, evidence -> result_json")
    class ResearchStudent(dspy.Module):
        def __init__(self):
            super().__init__()
            self.investigator = dspy.RLM("objective, corpus -> result_json", sub_lm=lm,
                interpreter_factory=factory, max_iters=budget["max_iters"],
                max_llm_calls=budget["max_subcalls"], max_output_chars=budget["max_output_chars"])
        def forward(self, objective, evidence):
            result = self.investigator(objective=objective +
                '\nReturn result_json as valid JSON with an "answer" string. Use only the supplied evidence.', corpus=evidence)
            if not result.trajectory or not result.trajectory[-1]["output"].startswith("FINAL:"):
                factory.channel.call("trace", {"kind": "policy_failure", "reason": "iteration_budget"})
                raise RuntimeError("RLM iteration budget exhausted")
            return result
    return ResearchStudent()


def instruction_map(student, kind):
    if kind == "dspy":
        return {"predict": student.signature.instructions}
    return {"action": student.investigator.generate_action.signature.instructions,
            "extract": student.investigator.extract.signature.instructions}


def apply_instructions(student, kind, values):
    if kind == "dspy":
        student.signature = student.signature.with_instructions(values["predict"])
    else:
        for key, predictor in (("action", student.investigator.generate_action),
                               ("extract", student.investigator.extract)):
            predictor.signature = predictor.signature.with_instructions(values[key])
