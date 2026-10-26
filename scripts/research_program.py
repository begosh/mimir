"""Research program selection at the scheduler seam, with native parity."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys

from backend import SwarmResult
from evidence_provenance import EvidenceProvenance, SourceStore, identity
from mimir_config import ConfigurationRequired


@dataclass(frozen=True)
class ResearchRequest:
    task_id: str
    prompt: str
    role: str
    model: str
    effort: str | None
    schema: dict | None


@dataclass
class ResearchOutcome:
    state: str
    response: SwarmResult
    trace_path: str | None = None


@dataclass
class ResearchContext:
    broker: object
    sources: EvidenceProvenance
    run_directory: Path
    config: dict


class StandardNativeProgram:
    async def run(self, request, context):
        prompt = request.prompt
        if context.sources.records:
            prompt += "\nCaptured evidence metadata (read only these explicitly named sources):\n" + json.dumps(context.sources.list_sources())
        result = await context.broker.spawn(prompt=prompt, role=request.role,
                                           model=request.model, effort=request.effort,
                                           json_schema=request.schema, input_data=None)
        return ResearchOutcome("completed" if result.status == "SUCCESS" else "failed", result)


class DspyResearchProgram:
    async def run(self, request, context):
        from dspy_runtime.host import run_program
        result, trace = await run_program(request, context)
        return ResearchOutcome("completed", result, trace)


def research_python():
    configured = os.environ.get("MIMIR_RESEARCH_PYTHON")
    if configured:
        return str(Path(configured).resolve(strict=True))
    local = Path.cwd() / ".venv-research" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return str(local) if local.is_file() else sys.executable


def research_runtime():
    """Inspect the optional environment without credentials or inference."""
    import subprocess
    code = "import importlib.metadata as m,json,sys; names=['dspy','gepa','deno']+(['pywin32'] if sys.platform=='win32' else []); print(json.dumps({n:m.version(n) for n in names}))"
    try:
        result = subprocess.run([research_python(), "-c", code], capture_output=True, text=True,
                                timeout=10, **({"creationflags": 0x08000000} if os.name == "nt" else {}))
        versions = json.loads(result.stdout) if result.returncode == 0 else {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        versions = {}
    expected = {"dspy": "3.4.1", "gepa": "0.1.4", "deno": "2.9.8"}
    if os.name == "nt":
        expected["pywin32"] = "312"
    return {"interpreter": research_python(), "versions": versions, "expected": expected,
            "ready": versions == expected, "tool_policy": "native Codex restricted completion; captured source queries only"}


def load_instruction_manifest(path):
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if set(manifest) != {"version", "program", "instructions", "evaluation", "reviewed", "sha256"}:
        raise ValueError("Invalid instruction manifest")
    content = {k: v for k, v in manifest.items() if k != "sha256"}
    if manifest["version"] != 1 or manifest["reviewed"] is not True or identity(content) != manifest["sha256"]:
        raise ValueError("Instruction manifest requires reviewed identity")
    if manifest["program"] not in {"dspy", "rlm"}:
        raise ValueError("Instruction manifest program must be dspy or rlm")
    allowed = {"predict", "action", "extract"}
    if not isinstance(manifest["instructions"], dict) or set(manifest["instructions"]) - allowed:
        raise ValueError("Instruction manifest contains non-instruction settings")
    if any(not isinstance(v, str) or not v.strip() or len(v) > 32000 for v in manifest["instructions"].values()):
        raise ValueError("Invalid optimized instructions")
    return manifest


def prepare_research(program, budget, source_manifest, instruction_manifest, state, directory):
    from invocation_broker import validate_budget
    program = program or state.get("research_program", "native")
    if program not in {"native", "dspy", "rlm"}:
        raise ConfigurationRequired("Research program must be native, dspy or rlm")
    previous = state.get("research_config")
    if previous:
        if previous.get("budget") is None:
            raise ConfigurationRequired("Legacy run has no durable budget; start a new run")
        if program != previous["program"] or (budget is not None and validate_budget(budget) != previous["budget"]):
            raise ConfigurationRequired("Research program and budget are fixed by the plan")
        config = previous
        if instruction_manifest and load_instruction_manifest(instruction_manifest) != config.get("instructions"):
            raise ConfigurationRequired("Instruction manifest changed; start a new run")
        if source_manifest:
            current = EvidenceProvenance.from_manifest(source_manifest)
            if current.allowed_domains != config.get("allowed_domains", []):
                raise ConfigurationRequired("Source capture domain policy changed; start a new run")
            if current.source_statuses != config.get("source_statuses", current.source_statuses):
                raise ConfigurationRequired("Source status changed; start a new run")
            saved = EvidenceProvenance(config["sources"])
            if [(r["id"], r["locator"], r["sha256"]) for r in current.to_list()] != [(r["id"], r["locator"], r["sha256"]) for r in saved.to_list()]:
                raise ConfigurationRequired("Source manifest changed; start a new run")
    else:
        sources = EvidenceProvenance.from_manifest(source_manifest) if source_manifest else EvidenceProvenance()
        if program != "native" and not sources.records:
            raise ConfigurationRequired("DSPy/RLM requires an explicit captured source manifest")
        config = {"version": 1, "program": program,
                  "budget": validate_budget(budget),
                  "sources": sources.to_list(),
                  "instructions": load_instruction_manifest(instruction_manifest) if instruction_manifest else None,
                  "interpreter_policy": "deno-no-host-access-v1", "dspy_version": "3.4.1"}
        if source_manifest:
            config["allowed_domains"] = sources.allowed_domains
            config["source_statuses"] = sources.source_statuses
    if program != "native" and not research_runtime()["ready"]:
        raise ConfigurationRequired("Research dependencies unavailable or unqualified; install requirements-research.txt in MIMIR_RESEARCH_PYTHON or .venv-research")
    sources = EvidenceProvenance.from_state(config)
    if config.get("instructions") and config["instructions"]["program"] != program:
        raise ConfigurationRequired("Instruction manifest does not match the research program")
    sources.verify_local_sources_unchanged()
    fingerprint = {k: v for k, v in config.items() if k != "sources"}
    fingerprint["source_digest"] = sources.digest
    import hashlib
    digest = hashlib.sha256()
    root = Path(__file__).resolve().parent
    for target in sorted([root / "research_program.py", root / "invocation_broker.py", root / "evidence_provenance.py",
                          root / "owned_process.py", root / "codex_sdk_backend.py", *(root / "dspy_runtime").glob("*.py")]):
        digest.update(target.name.encode())
        digest.update(target.read_bytes())
    fingerprint["runtime_sha256"] = digest.hexdigest()
    fingerprint["dependencies_sha256"] = hashlib.sha256((root.parent / "requirements-research.txt").read_bytes()).hexdigest()
    fingerprint["broker_protocol"] = 1
    if previous and (program != "native" or sources.records or config["budget"]) and state.get("research_identity") and state["research_identity"] != fingerprint:
        raise ConfigurationRequired("Research runtime or dependency policy changed; start a new run")
    return config, sources, fingerprint


class ResearchDispatcher:
    def __init__(self, context):
        self.context = context
        self.standard = StandardNativeProgram()
        self.selected = self.standard if context.config["program"] == "native" else DspyResearchProgram()

    async def __call__(self, node, prompt):
        needs_tools = getattr(node, "needs_tools", None)
        if node.input_artifacts.get("worker_wrapper") == "atomic_v1":
            from atomic_worker import TEXT_ONLY
            op = node.input_artifacts.get("task_contract", {}).get("operation")
            needs_tools = (op not in TEXT_ONLY) if op else False
        elif node.id == "critique" or "critic" in node.role.lower():
            needs_tools = False
        elif needs_tools is None:
            needs_tools = True

        if not needs_tools and self.context.config["program"] == "native":
            native = getattr(self.context.broker, "native", self.context.broker)
            if not callable(getattr(native, "spawn_restricted", None)):
                raise ConfigurationRequired("Supplied-input text workers require a text-only adapter")
            return await self.context.broker.spawn_restricted(prompt=prompt, role=node.role,
                model=self.context.broker.default_model, effort=self.context.broker.default_effort,
                json_schema=node.json_schema)

        program = self.standard if "critic" in node.role.lower() else self.selected
        outcome = await program.run(ResearchRequest(node.id, prompt, node.role,
                                                   getattr(node, "model", None) or self.context.broker.default_model,
                                                   getattr(node, "effort", None),
                                                   getattr(node, "json_schema", None)), self.context)
        outcome.response.trace_path = outcome.trace_path
        return outcome.response
