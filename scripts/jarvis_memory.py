"""
scripts/jarvis_memory.py
Project-scoped guidance and separately stored, unvalidated learning candidates.
Read mode is the engine default; no package-relative writable state is created.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class JarvisMemory:
    """
    Read curated guidance without automatically promoting generated candidates.
    """

    def __init__(self, memory_file_path: Optional[str] = None, *,
                 mode: Optional[str] = None, workspace: Optional[Path] = None,
                 legacy_path: Optional[Path] = None, guidance_path: Optional[Path] = None):
        # Positional callers retain the historical API. Engine callers always
        # supply an explicit mode; their writes are isolated candidate records.
        self._legacy_write = mode is None and memory_file_path is not None
        self.mode = mode or ("write" if self._legacy_write else "read")
        if self.mode not in ("off", "read", "write"):
            raise ValueError("Memory mode must be off, read, or write.")
        project = Path(workspace or Path.cwd()).resolve()
        self.memory_path = Path(memory_file_path).resolve() if memory_file_path else project / ".mimir" / "LEARNINGS.md"
        self.guidance_path = Path(guidance_path).resolve() if guidance_path else self.memory_path
        self.candidate_path = self.memory_path.parent / "learning-candidates.jsonl"
        self.legacy_path = Path(legacy_path).resolve() if legacy_path else project / "LEARNINGS.md"
        self._explicit_legacy_guidance = (memory_file_path is not None or guidance_path is not None) and self.guidance_path == self.legacy_path
        if self._legacy_write:
            self._ensure_file_exists()
        self.last_error: Optional[str] = None

    def _ensure_file_exists(self):
        if not self.memory_path.exists():
            self.memory_path.parent.mkdir(parents=True, exist_ok=True)
            initial_content = (
                "# M Í M I R // Persistent Memory Bank & Cumulative Learnings\n\n"
                "This document is Mímir's persistent memory bank at Mimisbrunnr. Candidate architecture "
                "patterns, avoided pitfalls (Red-Team), and core heuristics accumulate here over time.\n\n"
                "## 1. Core Heuristics\n"
                "- **Evidence Contracts:** Preserve source and test provenance; hashes identify outputs and do not verify claims.\n"
                "- **Kahn DAG Integrity:** Validate acyclic structure at runtime to guarantee dynamic sub-tasks do not deadlock the scheduler.\n"
                "- **Prompt-as-a-Variable:** Never flood raw context between models; use versioned Blackboard deltas.\n"
                "- **Source-Agnostic Scouting:** Select information channels dynamically based on domain (GitHub/RFCs for software, PubMed for biomedicine, SEC for finance).\n\n"
                "## 2. Red-Team Pitfalls & Mitigations (Anti-Patterns)\n"
                "- **Overconfidence Trap:** Micro-models often report high confidence despite logical flaws. Never trust self-assessed confidence without independent verification.\n"
                "- **Deadlock via Unhandled Errors:** If an upstream node crashes, dependencies must cascade to CANCELLED immediately.\n\n"
                "## 3. Log of Cumulative Learnings\n"
            )
            try:
                with self.memory_path.open("x", encoding="utf-8") as memory_file:
                    memory_file.write(initial_content)
            except FileExistsError:
                pass  # Another process initialized the same shared bank.

    def load_memory_context(self, topic: Optional[str] = None, max_lines: int = 60) -> str:
        """
        Reads the most relevant portions of LEARNINGS.md to feed into the Decomposer.
        """
        if self.mode == "off":
            return ""
        source = self.guidance_path if self.guidance_path.exists() else self.legacy_path
        if not source.exists():
            return ""
        try:
            content = source.read_text(encoding="utf-8")
            self.last_error = None
            if max_lines <= 0:
                return ""
            # Keep standing guidance, then choose relevant recent run records.
            sections = re.split(r"(?m)(?=^###\s+\[\d{4}-\d{2}-\d{2})", content.strip())
            header = sections[0].splitlines()
            entries = sections[1:]
            if source == self.legacy_path and not self._explicit_legacy_guidance:
                # Historical run records are generated candidates, not promoted
                # guidance. Preserve them on disk without automatically feeding
                # them into new objectives through the legacy fallback.
                entries = []
                header = ["Legacy standing guidance (unvalidated; independently check applicability):", *header]
            terms = set(re.findall(r"\w{3,}", (topic or "").casefold()))
            ranked = sorted(enumerate(entries), key=lambda pair: (
                len(terms.intersection(re.findall(r"\w{3,}", pair[1].casefold()))), pair[0]
            ), reverse=True)
            lines = header[:min(len(header), max(1, max_lines // 2))] if entries else header
            for _, entry in ranked:
                if len(lines) >= max_lines:
                    break
                lines.extend(entry.strip().splitlines()[:max_lines - len(lines)])
            return "\n".join(lines[:max_lines])
        except (OSError, UnicodeError) as exc:
            self.last_error = str(exc)
            return ""

    def record_learning(
        self,
        goal: str,
        hardened_solution_snippet: str,
        reflection_notes: str,
        red_team_traps: Optional[List[str]] = None,
        report_path: Optional[str] = None,
        candidate_id: Optional[str] = None,
    ) -> bool:
        """
        Appends new distilled learnings from a completed run into LEARNINGS.md.
        """
        if self.mode != "write":
            self.last_error = None
            return False
        if not self._legacy_write:
            return self._record_candidate(goal, hardened_solution_snippet,
                                          reflection_notes, red_team_traps,
                                          report_path, candidate_id)
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        clean_goal = " ".join(goal.split())
        clean_solution = " ".join(hardened_solution_snippet.split())
        entry_lines = [
            f"\n### [{timestamp}] Objective: {clean_goal[:500].strip()}",
            f"- **Run Takeaway (requires independent validation):** {clean_solution[:300]}",
        ]
        if report_path:
            entry_lines.append(f"- **Evidence and limitations:** {' '.join(report_path.split())}")

        if reflection_notes:
            clean_reflection = reflection_notes.replace("\n", " ").strip()
            entry_lines.append(f"- **Reflection Note:** {clean_reflection[:250]}...")

        if red_team_traps:
            entry_lines.append("- **Identified Pitfalls:**")
            for trap in red_team_traps[:2]:
                entry_lines.append(f"  * {' '.join(trap.split())[:150]}")

        entry_text = "\n".join(entry_lines) + "\n"

        try:
            with open(self.memory_path, "a", encoding="utf-8") as f:
                f.write(entry_text)
            self.last_error = None
            return True
        except (OSError, UnicodeError) as exc:
            self.last_error = str(exc)
            return False

    def _record_candidate(self, goal: str, solution: str, reflection: str,
                          traps: Optional[List[str]], report_path: Optional[str],
                          candidate_id: Optional[str]) -> bool:
        """Append an unvalidated candidate once under a cross-process lease.

        Candidate text is never loaded as standing guidance. Promotion requires
        an explicit human edit of guidance_path, with source validation.
        """
        from run_locks import ownership, RunBusyError
        identity = json.dumps([report_path, goal, solution], ensure_ascii=False)
        identifier = candidate_id or hashlib.sha256(identity.encode("utf-8")).hexdigest()
        entry = {"candidate_id": identifier,
                 "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 "status": "requires_independent_validation", "goal": " ".join(goal.split())[:500],
                 "takeaway": " ".join(solution.split())[:300],
                 "reflection": " ".join(reflection.split())[:250],
                 "pitfalls": [" ".join(trap.split())[:150] for trap in (traps or [])[:2]],
                 "report_path": report_path}
        try:
            if self.candidate_path.is_symlink():
                self.last_error = "Candidate memory must not be a symbolic link."
                return False
            self.candidate_path.parent.mkdir(parents=True, exist_ok=True)
            with ownership(self.candidate_path.with_suffix(".lock")):
                seen: set[str] = set()
                if self.candidate_path.exists():
                    with self.candidate_path.open(encoding="utf-8") as stream:
                        for line in stream:
                            try:
                                value = json.loads(line)
                                if isinstance(value, dict) and isinstance(value.get("candidate_id"), str):
                                    seen.add(value["candidate_id"])
                            except json.JSONDecodeError:
                                # A truncated append is evidence of interrupted
                                # storage, not permission to silently repair it.
                                self.last_error = "Candidate memory has an incomplete record; repair it explicitly before appending."
                                return False
                if identifier not in seen:
                    with self.candidate_path.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
                        stream.flush()
            self.last_error = None
            return True
        except (OSError, UnicodeError, RunBusyError) as exc:
            self.last_error = str(exc)
            return False

    def get_summary_stats(self) -> Dict[str, Any]:
        """Returns statistics about the current memory bank."""
        source = self.memory_path if self._legacy_write else self.candidate_path
        if self.mode == "off" or not source.exists():
            return {"entries": 0, "size_bytes": 0, "mode": self.mode}

        try:
            content = source.read_text(encoding="utf-8")
            entries = len(re.findall(r"^###\s+\[\d{4}-\d{2}-\d{2}", content, flags=re.MULTILINE)) if self._legacy_write else len(content.splitlines())
            size = source.stat().st_size
            return {"entries": entries, "size_bytes": size, "mode": self.mode}
        except (OSError, UnicodeError) as exc:
            self.last_error = str(exc)
            return {"entries": None, "size_bytes": None, "error": str(exc)}


# Alias for naming consistency
MimirMemory = JarvisMemory
