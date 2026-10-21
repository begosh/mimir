"""
scripts/jarvis_memory.py
Long-Term Memory and Cross-Session Learnings Engine for M Í M I R.
Reads and commits cumulative heuristics, anti-patterns, and insights to LEARNINGS.md.
"""

from __future__ import annotations

import datetime
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class JarvisMemory:
    """
    Manages persistent memory across Mímir swarm sessions.
    Stores distilled knowledge in LEARNINGS.md.
    """

    def __init__(self, memory_file_path: Optional[str] = None):
        if memory_file_path:
            self.memory_path = Path(memory_file_path)
        else:
            # Default to skill root directory
            skill_root = Path(__file__).resolve().parent.parent
            self.memory_path = skill_root / "LEARNINGS.md"

        self._ensure_file_exists()

    def _ensure_file_exists(self):
        if not self.memory_path.exists():
            self.memory_path.parent.mkdir(parents=True, exist_ok=True)
            initial_content = (
                "# M Í M I R // Persistent Memory Bank & Cumulative Learnings\n\n"
                "This document is Mímir's persistent memory bank at Mimisbrunnr. Proven architecture "
                "patterns, avoided pitfalls (Red-Team), and core heuristics accumulate here over time.\n\n"
                "## 1. Verified Core Heuristics\n"
                "- **Evidence Contracts:** Always anchor claims with hashed raw data/test outcomes to halt hallucination cascades.\n"
                "- **Kahn DAG Integrity:** Validate acyclic structure at runtime to guarantee dynamic sub-tasks do not deadlock the scheduler.\n"
                "- **Prompt-as-a-Variable:** Never flood raw context between models; use versioned Blackboard deltas.\n"
                "- **Source-Agnostic Scouting:** Select information channels dynamically based on domain (GitHub/RFCs for software, PubMed for biomedicine, SEC for finance).\n\n"
                "## 2. Red-Team Pitfalls & Mitigations (Anti-Patterns)\n"
                "- **Overconfidence Trap:** Micro-models often report high confidence despite logical flaws. Never trust self-assessed confidence without independent verification.\n"
                "- **Deadlock via Unhandled Errors:** If an upstream node crashes, dependencies must cascade to CANCELLED immediately.\n\n"
                "## 3. Log of Cumulative Learnings\n"
            )
            self.memory_path.write_text(initial_content, encoding="utf-8")

    def load_memory_context(self, topic: Optional[str] = None, max_lines: int = 60) -> str:
        """
        Reads the most relevant portions of LEARNINGS.md to feed into the Decomposer.
        """
        try:
            content = self.memory_path.read_text(encoding="utf-8")
            lines = content.strip().split("\n")
            return "\n".join(lines[:max_lines])
        except Exception:
            return ""

    def record_learning(
        self,
        goal: str,
        hardened_solution_snippet: str,
        reflection_notes: str,
        red_team_traps: Optional[List[str]] = None,
    ) -> None:
        """
        Appends new distilled learnings from a completed run into LEARNINGS.md.
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        entry_lines = [
            f"\n### [{timestamp}] Objective: {goal}",
            f"- **Key Takeaway / Pareto-Hardened Solution:** {hardened_solution_snippet[:300].strip()}...",
        ]

        if reflection_notes:
            clean_reflection = reflection_notes.replace("\n", " ").strip()
            entry_lines.append(f"- **Reflection Note:** {clean_reflection[:250]}...")

        if red_team_traps:
            entry_lines.append("- **Identified Pitfalls:**")
            for trap in red_team_traps[:2]:
                entry_lines.append(f"  * {trap[:150].strip()}")

        entry_text = "\n".join(entry_lines) + "\n"

        try:
            with open(self.memory_path, "a", encoding="utf-8") as f:
                f.write(entry_text)
        except Exception:
            pass

    def get_summary_stats(self) -> Dict[str, Any]:
        """Returns statistics about the current memory bank."""
        if not self.memory_path.exists():
            return {"entries": 0, "size_bytes": 0}

        try:
            content = self.memory_path.read_text(encoding="utf-8")
            entries = len(re.findall(r"^###\s+\[\d{4}-\d{2}-\d{2}", content, flags=re.MULTILINE))
            size = self.memory_path.stat().st_size
            return {"entries": entries, "size_bytes": size}
        except Exception:
            return {"entries": 0, "size_bytes": 0}


# Alias for naming consistency
MimirMemory = JarvisMemory
