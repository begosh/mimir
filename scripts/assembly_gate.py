"""Persisted one-correction final gate; interruptions never reset its allowance."""
from copy import deepcopy

from backend import WorkerFailure
from mimir_config import ConfigurationRequired
from post_worker import assembly_repair_policy, check_final_answer, repair_assembled_answer, synthesize
from source_store import identity
from publication_view import build_publication_view


async def assemble_checked(backend, context, state, persist, emit, *, model, max_answer_words=None):
    policy = assembly_repair_policy()
    binding = identity({"context": context, "model": model, "effort": backend.default_effort,
                        "max_answer_words": max_answer_words, "policy": policy})
    history = state.get("assembly_history")
    if history:
        if history.get("binding") != binding or history.get("policy") != policy:
            raise ConfigurationRequired("Assembly inputs or checker/repair policy changed; replan explicitly")
        if history.get("identity") != identity({k: v for k, v in history.items() if k != "identity"}):
            raise ConfigurationRequired("Assembly history identity changed; replan explicitly")
        if history["stage"] in {"synthesizing", "checking", "repairing", "rechecking", "failed"}:
            raise WorkerFailure("Final answer", "Assembly attempt interrupted or exhausted; retained versions require review and a new run")
    else:
        history = {"binding": binding, "policy": policy, "corrections_reserved": 0, "versions": [], "stage": "new"}
        state["assembly_history"] = history

    def save(stage):
        history["stage"] = stage
        history["identity"] = identity({k: v for k, v in history.items() if k != "identity"})
        persist()

    try:
        if history["stage"] == "new":
            save("synthesizing")
            assembled, _ = await synthesize(backend, context, model=model, max_answer_words=max_answer_words)
            history["versions"].append({"kind": "original", "result": deepcopy(assembled),
                                        "publication_view": build_publication_view(context)})
            save("assembled")
        if history["stage"] == "passed":
            version = history["versions"][-1]
            state["publication_view"] = deepcopy(version["publication_view"])
            return deepcopy(version["result"]), deepcopy(version["check"])
        version = history["versions"][-1]
        if history["stage"] in {"assembled", "corrected"}:
            save("rechecking" if history["corrections_reserved"] else "checking")
            emit("final_check_started")
            check = await check_final_answer(backend, context, version["result"], model=model,
                                             publication_view=version["publication_view"])
            version["check"] = deepcopy(check)
            state["final_answer_check"] = check
            emit("final_check_completed", verdict=check["verdict"], issues=check["issues"])
            if check["verdict"] == "PASS":
                state["publication_view"] = deepcopy(version["publication_view"])
                save("passed")
                state.pop("rejected_synthesis", None)
                persist()
                return deepcopy(version["result"]), check
            state["rejected_synthesis"] = {"result": deepcopy(version["result"]), "result_check": check,
                                           "reason": "Final answer acceptance check failed"}
            save("rejected")
        if history["corrections_reserved"]:
            save("failed")
            raise WorkerFailure("Final answer", "Acceptance check failed after the single assembly correction")
        history["corrections_reserved"] = 1
        save("repairing")  # Durable reservation before the paid correction call.
        emit("assembly_correction_started")
        corrected = await repair_assembled_answer(backend, context, version["result"], version["check"]["issues"],
                                                  model=model, max_answer_words=max_answer_words, publication=True)
        quarantines = corrected.pop("quarantined_tasks")
        history["versions"].append({"kind": "correction", "result": deepcopy(corrected),
                                    "publication_view": build_publication_view(context, quarantines)})
        save("corrected")
        emit("assembly_correction_completed")
        return await assemble_checked(backend, context, state, persist, emit, model=model, max_answer_words=max_answer_words)
    except BaseException as exc:
        if getattr(exc, "rejected_output", None):
            history["rejected_correction"] = deepcopy(exc.rejected_output)
        if history["versions"] and not state.get("rejected_synthesis"):
            state["rejected_synthesis"] = {"result": deepcopy(history["versions"][-1]["result"]),
                                           "checker_error": str(exc), "reason": "Assembly did not pass its final gate"}
        # Interrupted operations remain consumed. Saved completed boundaries can resume.
        save(history["stage"])
        raise
