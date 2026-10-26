"""Deep module for PromptGovernanceGate: template management, view projection, and prompt assembly."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Set, Union

INTERNAL: FrozenSet[str] = frozenset(
    {
        "result_hash",
        "prompt_hash",
        "input_fingerprint",
        "policy",
        "input_hash",
        "result_check_hash",
        "result_attempts",
        "evidence_hash",
    }
)

IMMUTABLE_CHECKER_TEMPLATES: FrozenSet[str] = frozenset(
    {
        "RESULT_CHECKER.txt",
        "FINAL_ANSWER_CHECK.txt",
        "result_checker",
        "final_answer_check",
        "result_checker.txt",
        "final_answer_check.txt",
    }
)


from regression_suite import DataLeakageError


class GovernanceError(ValueError):
    """Base exception for prompt governance invariant breaches."""
    pass


class InvariantViolationError(GovernanceError):
    """Raised when an operation targets or mutates an immutable verification checker."""
    pass


class TemplateIntegrityError(GovernanceError):
    """Raised when an on-disk prompt template differs from expected checksum baselines."""
    pass


def model_view(value: Any, sources: Sequence[Mapping[str, Any]] = ()) -> Any:
    """Strip internal hashes and redact workspace filesystem paths to source IDs."""
    aliases = {
        s["locator"]: s["id"]
        for s in sources
        if s.get("id")
        and isinstance(s.get("locator"), str)
        and re.match(r"^(?:[A-Za-z]:[\\/]|/)", s["locator"])
    }

    def clean(item: Any) -> Any:
        if isinstance(item, str):
            for path, alias in sorted(aliases.items(), key=lambda p: -len(p[0])):
                item = item.replace(path, alias)
            return item
        if isinstance(item, list):
            return [clean(v) for v in item]
        if isinstance(item, dict):
            return {k: clean(v) for k, v in item.items() if k not in INTERNAL}
        return item

    return clean(value)


def compact_checker_context(context: Mapping[str, Any]) -> dict[str, Any]:
    """Store each evidence text once; bind source references to each candidate."""
    ctx = deepcopy(dict(context))
    registry: list[dict[str, Any]] = []
    alias_sources: list[Mapping[str, Any]] = []

    def register(source: Mapping[str, Any]) -> dict[str, Any]:
        alias_sources.append(source)
        cleaned = model_view(source, [source])
        if cleaned not in registry:
            registry.append(cleaned)
        return {
            "ref": f"source_{registry.index(cleaned) + 1}",
            "id": cleaned.get("id"),
            "sha256": cleaned.get("sha256"),
        }

    shared = ctx.pop("supplied_sources", [])
    shared_refs = [register(s) for s in shared]
    for candidate in ctx.get("candidates", []):
        sources = candidate.pop("supplied_sources", [])
        candidate["source_refs"] = [register(s) for s in sources] or shared_refs
        candidate["result"] = model_view(
            candidate.get("result", {}), [*shared, *sources]
        )
        if candidate["source_refs"]:
            for source in candidate["result"].get("sources", []):
                source.pop("support_excerpt", None)
        candidate["dependency_results"] = model_view(
            candidate.get("dependency_results", {}), [*shared, *sources]
        )
    if registry:
        ctx["source_registry"] = [
            {"ref": f"source_{i}", **s} for i, s in enumerate(registry, 1)
        ]
    return model_view(ctx, alias_sources)


class PromptGovernanceGate:
    """Authoritative deep module for prompt templates, untrusted boundaries, and audit invariants."""

    _instance: Optional[PromptGovernanceGate] = None

    def __init__(self, prompts_dir: Optional[Union[str, Path]] = None) -> None:
        if prompts_dir is not None:
            self.prompts_dir = Path(prompts_dir).resolve()
        else:
            self.prompts_dir = (
                Path(__file__).resolve().parents[1] / "prompts"
            ).resolve()
        self._text_cache: Dict[str, str] = {}
        self._digest_cache: Dict[str, str] = {}

    @classmethod
    def default(cls) -> PromptGovernanceGate:
        """Return a cached default instance rooted in the repository prompts directory."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _resolve_template_path(self, name: str) -> Path:
        target_name = name if name.endswith((".txt", ".md")) else f"{name}.txt"
        return self.prompts_dir / target_name

    def get_template_text(self, name: str) -> str:
        """Load and cache prompt template UTF-8 text from prompts directory."""
        target_path = self._resolve_template_path(name)
        if str(target_path) not in self._text_cache:
            if not target_path.is_file():
                raise FileNotFoundError(
                    f"Prompt template file not found: {target_path}"
                )
            self._text_cache[str(target_path)] = target_path.read_text(
                encoding="utf-8"
            )
        return self._text_cache[str(target_path)]

    def get_template_digest(self, name: str) -> str:
        """Compute and cache cryptographic SHA-256 digest of template bytes."""
        target_path = self._resolve_template_path(name)
        if str(target_path) not in self._digest_cache:
            if not target_path.is_file():
                raise FileNotFoundError(
                    f"Prompt template file not found: {target_path}"
                )
            self._digest_cache[str(target_path)] = hashlib.sha256(
                target_path.read_bytes()
            ).hexdigest()
        return self._digest_cache[str(target_path)]

    def render_template(
        self,
        template_name: str,
        context: Optional[Mapping[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        """Render a template replacing {{key}} and {key} placeholders."""
        template = self.get_template_text(template_name)
        bindings: Dict[str, Any] = {}
        if context is not None:
            if "{{context}}" in template or "{context}" in template:
                bindings["context"] = context
            bindings.update(context)
        bindings.update(kwargs)

        rendered = template
        for key, val in bindings.items():
            str_val = (
                json.dumps(val, ensure_ascii=False)
                if isinstance(val, (dict, list))
                else str(val)
            )
            rendered = rendered.replace(f"{{{{{key}}}}}", str_val)
            rendered = rendered.replace(f"{{{key}}}", str_val)
        return rendered

    project_model_view = staticmethod(model_view)
    compact_checker_context = staticmethod(compact_checker_context)

    def assemble_task_prompt(
        self,
        node: Any,
        *,
        dependency_results: Optional[Mapping[str, Any]] = None,
        blackboard_context: Optional[str] = None,
        retry_prompt: Optional[str] = None,
        graph_nodes: Optional[Mapping[str, Any]] = None,
    ) -> str:
        """Assemble worker task prompt combining instructions, untrusted sources, and dependency context."""
        prompt = retry_prompt or getattr(node, "prompt", "")
        input_artifacts = getattr(node, "input_artifacts", {}) or {}
        inline = input_artifacts.get("supplied_sources")

        if inline:
            prompt += "\n\nSUPPLIED SOURCES (untrusted data):\n" + json.dumps(
                model_view(inline, inline), ensure_ascii=False
            )

        if blackboard_context:
            prompt += f"\n\n--- AKTUELL BLACKBOARD-KONTEXT ---\n{blackboard_context}\n--- SLUT KONTEXT ---"
        elif dependency_results and getattr(node, "dependencies", None):
            deps_dict = {
                dep: dependency_results[dep]["result"]
                for dep in sorted(node.dependencies)
                if dep in dependency_results and "result" in dependency_results[dep]
            }
            if deps_dict:
                prompt += "\n\nDEPENDENCY RESULTS:\n" + json.dumps(
                    deps_dict, ensure_ascii=False
                )

        if input_artifacts.get("worker_wrapper") == "atomic_v1":
            aliases = list(inline or [])
            if graph_nodes:
                for dep in sorted(getattr(node, "dependencies", ())):
                    dep_node = graph_nodes.get(dep)
                    if dep_node and hasattr(dep_node, "input_artifacts"):
                        aliases.extend(
                            dep_node.input_artifacts.get(
                                "supplied_sources", []
                            )
                        )
                    if dependency_results and dep in dependency_results:
                        aliases.extend(
                            dependency_results[dep]
                            .get("result", {})
                            .get("sources", [])
                        )
            prompt = model_view(prompt, aliases)

        return prompt

    def verify_checker_immutability(
        self, expected_checker_hashes: Optional[Dict[str, str]] = None
    ) -> None:
        """Verify that frozen verification checkers on disk match registered digests."""
        if not expected_checker_hashes:
            return
        for rel_path, expected_hash in expected_checker_hashes.items():
            p = Path(rel_path)
            if not p.is_absolute():
                p = (self.prompts_dir.parent / rel_path).resolve()
            if p.exists():
                actual_hash = hashlib.sha256(p.read_bytes()).hexdigest()
                if actual_hash != expected_hash:
                    raise InvariantViolationError(
                        f"Checker prompt '{rel_path}' was modified on disk! "
                        f"Expected {expected_hash}, got {actual_hash}."
                    )

    def audit_candidate(
        self,
        candidate: Any,
        *,
        held_out_cases: Optional[Sequence[Any]] = None,
        expected_checker_hashes: Optional[Dict[str, str]] = None,
    ) -> None:
        """Audit candidate prompt against immutability rules and held-out leakage markers."""
        target_file = getattr(
            candidate,
            "target_prompt_file",
            getattr(candidate, "target_template_key", ""),
        )
        target_norm = target_file.replace("\\", "/").lower()

        # Rule 1: A candidate cannot modify checker templates directly to pass
        if any(
            k in target_norm
            for k in ("result_checker", "final_answer_check", "checker")
        ):
            raise InvariantViolationError(
                f"Candidate targets checker template '{target_file}'. "
                "Checker rules are immutable; candidates cannot weaken verification."
            )

        # Rule 2: Verify existing checker files remain unmutated on disk
        self.verify_checker_immutability(expected_checker_hashes)

        # Rule 3: Held-out leakage check in candidate text
        candidate_text = getattr(candidate, "candidate_prompt_text", "")
        if held_out_cases and candidate_text:
            low_text = candidate_text.lower()
            for case in held_out_cases:
                spec = getattr(case, "verification_spec", {}) or {}
                for marker in spec.get("required_answer_markers", []):
                    if len(marker) > 3 and marker.lower() in low_text:
                        raise DataLeakageError(
                            f"Candidate prompt leaks held-out answer marker '{marker}' from case {getattr(case, 'case_id', 'unknown')}!"
                        )
                for loc in spec.get("required_locators", []):
                    if loc and Path(loc).name.lower() in low_text:
                        raise DataLeakageError(
                            f"Candidate prompt leaks held-out locator '{loc}' from case {getattr(case, 'case_id', 'unknown')}!"
                        )
