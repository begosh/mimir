#!/usr/bin/env python3
"""
scripts/build_presentation.py
Builds the official SKF-branded presentation for:
"The Self-Hardening Agent Swarm: Reviewing Evidence Through Task Decomposition & Adversarial Reflection"
Adheres strictly to the SKF presentation skill rules and template.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path


def build_deck(output_path: Path, skill_dir: Path, template_path: Path | None = None):
    """Build with an explicitly selected optional presentation skill package."""
    skill_dir = Path(skill_dir).resolve(strict=True)
    scripts_dir = skill_dir / "scripts"
    helper_path = scripts_dir / "skf_deck.py"
    template_path = Path(template_path) if template_path else skill_dir / "assets" / "SKF Template.pptx"
    if not helper_path.is_file() or not template_path.is_file():
        raise ValueError("Presentation skill requires scripts/skf_deck.py and an existing template")
    spec = importlib.util.spec_from_file_location("mimir_skf_deck", helper_path)
    if spec is None or spec.loader is None:
        raise ValueError("Could not load the presentation helper")
    helper = importlib.util.module_from_spec(spec)
    # The optional helper may import sibling modules. Limit discovery changes
    # to this explicit invocation; importing this utility has no side effects.
    original_path = list(sys.path)
    previous_module = sys.modules.get(spec.name)
    try:
        sys.path.insert(0, str(scripts_dir))
        sys.modules[spec.name] = helper
        spec.loader.exec_module(helper)
    finally:
        sys.path[:] = original_path
        if previous_module is None:
            sys.modules.pop(spec.name, None)
        else:
            sys.modules[spec.name] = previous_module
    new_deck, add_slide, set_text, set_notes, add_source_line, prune_empty_placeholders, notes_report, save = (
        getattr(helper, name) for name in (
            "new_deck", "add_slide", "set_text", "set_notes", "add_source_line",
            "prune_empty_placeholders", "notes_report", "save"
        )
    )
    prs = new_deck(template_path)

    # -------------------------------------------------------------------------
    # SLIDE 1: Title Cover (Start Blue)
    # -------------------------------------------------------------------------
    s1 = add_slide(prs, "Start Blue")
    set_text(s1, 0, "The Self-Hardening Agent Swarm")
    set_text(s1, 1, "Reviewing Evidence Through Task Decomposition & Adversarial Reflection\nJonas Aspman")
    set_notes(
        s1,
        "Welcome, everyone. Today we are addressing the fundamental bottleneck in enterprise AI: "
        "why we still do not trust single-turn LLM prompts with mission-critical system architecture. "
        "Over the next twelve minutes, I will walk you through the architectural design of a self-hardening agent swarm "
        "that supports review through formal graph validation, provenance recording, "
        "cryptographic evidence contracts, and automated adversarial red-teaming."
    )
    prune_empty_placeholders(s1)

    # -------------------------------------------------------------------------
    # SLIDE 2: The Core Problem (Headline only Blue)
    # -------------------------------------------------------------------------
    s2 = add_slide(prs, "Headline only Blue")
    set_text(s2, 1, "THE FRAGILITY TRAP")
    set_text(s2, 0, "Single-turn prompts fail complex systems by flattering flawed premises")
    set_notes(
        s2,
        "When we ask a standard frontier model to design a distributed cache or an enterprise integration, "
        "it sounds exceptionally confident. But under the hood, single-turn prompts suffer from sycophancy: "
        "they agree with your premise even when it contains fatal bugs. They gloss over network partitions, "
        "miss subtle race conditions, and hallucinate non-existent API parameters. "
        "In production, hope is not an engineering strategy."
    )
    prune_empty_placeholders(s2)

    # -------------------------------------------------------------------------
    # SLIDE 3: The Three Failure Modes (Content Boxes)
    # -------------------------------------------------------------------------
    s3 = add_slide(prs, "Content Boxes")
    set_text(s3, 1, "STRUCTURAL LIMITATIONS")
    set_text(s3, 0, "Enterprise architecture breaks under three structural weaknesses of standard prompts")
    # Card 1
    set_text(s3, 16, "Sycophancy")
    set_text(s3, 25, "Frontier models instinctively flatter the user, confirming flawed architectural assumptions instead of exposing fatal design traps.")
    # Card 2
    set_text(s3, 20, "Context Bloat & Drift")
    set_text(s3, 28, "Monolithic prompts lose track of boundary invariants and race conditions across distributed components, inventing APIs under load.")
    # Card 3
    set_text(s3, 24, "Zero Long-Term Memory")
    set_text(s3, 27, "Every conversation starts from a blank slate, endlessly repeating yesterday's operational post-mortems and known anti-patterns.")
    set_notes(
        s3,
        "These are the three walls every team hits when trying to use LLMs for serious systems engineering. "
        "First, sycophancy: models want to please you, so they validate broken designs. "
        "Second, context bloat: stuffing everything into one prompt causes attention drift where subtle concurrency traps get lost. "
        "Third, amnesia: a chat session never learns from past production incidents. "
        "To solve this, we had to rethink the execution harness from the ground up."
    )
    prune_empty_placeholders(s3)

    # -------------------------------------------------------------------------
    # SLIDE 4: Pillar 1 - Task Decomposition & JEV Gating (Four Numbers Process)
    # -------------------------------------------------------------------------
    s4 = add_slide(prs, "Four Numbers Process")
    set_text(s4, 1, "PILLAR 1: TASK DECOMPOSITION")
    set_text(s4, 0, "Validating task graphs detects cycles before scheduling")
    # Step 1
    set_text(s4, 15, "01")
    set_text(s4, 13, "Objective Planning")
    set_text(s4, 16, "One decomposition call proposes a flat dependency graph with goal-specific worker roles.")
    # Step 2
    set_text(s4, 19, "02")
    set_text(s4, 25, "Graph Validation")
    set_text(s4, 20, "Checks task IDs, dependencies and cycles before any worker tasks execute.")
    # Step 3
    set_text(s4, 23, "03")
    set_text(s4, 21, "JEV Gating")
    set_text(s4, 24, "Score = criticality × (1 − 0.5 × redundancy). Both inputs are model estimates.")
    # Step 4
    set_text(s4, 26, "04")
    set_text(s4, 28, "Topological Execution")
    set_text(s4, 27, "Kahn DAG validation checks cycles; failed dependencies cancel downstream work.")
    set_notes(
        s4,
        "The engine performs one decomposition call and validates the resulting flat dependency graph. "
        "Worker roles depend on the objective; the default pipeline does not recursively expand the graph. "
        "Its JEV score is criticality times one minus half the redundancy penalty. "
        "These model estimates guide prioritization and require evaluation against actual outcomes. "
        "If a branch falls below our threshold, it is pruned immediately. "
        "Kahn's topological sort orders dependencies. Runtime timeouts and failure handling remain separate concerns."
    )
    prune_empty_placeholders(s4)

    # -------------------------------------------------------------------------
    # SLIDE 5: Pillar 2 - Anti-Hallucination via EvidenceContracts (Content Boxes)
    # -------------------------------------------------------------------------
    s5 = add_slide(prs, "Content Boxes")
    set_text(s5, 1, "PILLAR 2: EVIDENCE PROVENANCE")
    set_text(s5, 0, "Evidence contracts preserve provenance; hashes identify outputs")
    # Card 1
    set_text(s5, 16, "Omni-Channel Grounding")
    set_text(s5, 25, "A public scout retrieves search snippets and arXiv abstracts. Workers can inspect primary sources with their configured tools.")
    # Card 2
    set_text(s5, 20, "EvidenceContracts")
    set_text(s5, 28, "Workers report outputs and citations. Contract validation checks structure; factual correctness requires independent checks.")
    # Card 3
    set_text(s5, 24, "Shared Blackboard")
    set_text(s5, 27, "Completed deliverables carry SHA-256 output hashes on a shared blackboard and provide context to dependent tasks.")
    set_notes(
        s5,
        "Pillar two preserves evidence provenance and exposes gaps. Unsupported claims still require review. "
        "First, the public scout retrieves search snippets and preprint abstracts, retaining source links and retrieval gaps. "
        "Second, worker outputs are recorded in EvidenceContracts with metadata and available source links. "
        "Finally, every output is cryptographically hashed with SHA-256 and committed to a shared blackboard. "
        "A valid output hash proves content identity, not truth. Claims and citations still need independent validation."
    )
    prune_empty_placeholders(s5)

    # -------------------------------------------------------------------------
    # SLIDE 6: Pillar 3 - Critique and Reflection (Four Numbers Process Blue)
    # -------------------------------------------------------------------------
    s6 = add_slide(prs, "Four Numbers Process Blue")
    set_text(s6, 1, "PILLAR 3: ADVERSARIAL HARDENING")
    set_text(s6, 0, "Model critique and revision expose potential gaps before engineering review")
    # Step 1
    set_text(s6, 15, "01")
    set_text(s6, 13, "Draft Synthesis")
    set_text(s6, 16, "Assembles a draft from recorded worker outputs and their reported evidence.")
    # Step 2
    set_text(s6, 19, "02")
    set_text(s6, 25, "Model Critique")
    set_text(s6, 20, "A critic identifies potential inconsistencies and missing evidence; it does not run stress tests.")
    # Step 3
    set_text(s6, 23, "03")
    set_text(s6, 21, "One Reflection")
    set_text(s6, 24, "The default pipeline requests one revision using the critique; revisions still need testing.")
    # Step 4
    set_text(s6, 26, "04")
    set_text(s6, 28, "Reviewed Candidate")
    set_text(s6, 27, "Delivers a reviewed proposal with sources and limitations for engineering validation.")
    set_notes(
        s6,
        "This is where the swarm earns the name 'Self-Hardening'. Once a draft architecture is assembled, "
        "it enters a model critique and revision step. We invoke a dedicated critic "
        "whose sole purpose is to break the solution: finding clock drift, split-brain risks, or invalid concurrent writes. "
        "The engine requests a revision addressing the critique and records heuristic candidate scores. "
        "The result remains a proposal requiring independent tests and review."
    )
    prune_empty_placeholders(s6)

    # -------------------------------------------------------------------------
    # SLIDE 7: Pillar 4 - Cumulative Memory & Backend Configuration (Content Numbers)
    # -------------------------------------------------------------------------
    s7 = add_slide(prs, "Content Numbers")
    set_text(s7, 1, "PILLAR 4: ENTERPRISE DEPLOYABILITY")
    set_text(s7, 0, "Configured backends reuse authentication and preserve candidate lessons")
    set_text(s7, 13, "Workers reuse configured CLI logins and consume account allowances or provider charges.")
    # Big Number 1
    set_text(s7, 15, "CLI / HTTP")
    set_text(s7, 16, "Provider Configuration")
    set_text(s7, 17, "Invokes configured worker CLIs with existing authentication. Billing and allowances depend on the selected backend and model.")
    # Big Number 2
    set_text(s7, 19, "SHA-256")
    set_text(s7, 20, "Output Identity")
    set_text(s7, 21, "Output hashes preserve identity. Primary source retrieval, tests and proof checking require separate validation.")
    # Big Number 3
    set_text(s7, 23, "Continuous")
    set_text(s7, 24, "Persistent Learning")
    set_text(s7, 25, "Appends candidate lessons after completed runs; writes may fail and stored lessons require independent review.")
    add_source_line(s7, "Architecture: Mimir Autonomous Epistemic Swarm Engine, SKF Global IT")
    set_notes(
        s7,
        "Backends use existing CLI authentication or configured HTTP providers. "
        "Provider and CLI configuration determine whether API keys are required and what allowance or charges apply. "
        "Authentication reuse does not establish enterprise security, availability or cost guarantees. "
        "Furthermore, it records candidate lessons in LEARNINGS.md, retrieving relevant and recent entries. "
        "Lessons require independent review and may be incomplete, outdated or incorrect."
    )
    prune_empty_placeholders(s7)

    # -------------------------------------------------------------------------
    # SLIDE 8: Closing (Thank You Blue)
    # -------------------------------------------------------------------------
    s8 = add_slide(prs, "Thank You Blue")
    set_text(s8, 0, "Thank you")
    set_text(s8, 1, "Jonas Aspman\nGlobal IT & Architecture")
    set_text(s8, 16, "Repository: github.com/begosh/mimir")
    set_text(s8, 20, "Universal Installer: npx skills add begosh/mimir")
    set_notes(
        s8,
        "To close: we have moved beyond the fragile single-prompt paradigm. "
        "By combining validated task graphs, output provenance, one critique and reflection step, and candidate learning records, "
        "we support source-aware engineering review while preserving the need for independent validation. "
        "The Mímir engine is open, portable across Codex and Antigravity, and ready today. "
        "Thank you, and I look forward to your questions."
    )
    prune_empty_placeholders(s8)

    # -------------------------------------------------------------------------
    # Verification & Save
    # -------------------------------------------------------------------------
    missing_notes = notes_report(prs)
    if missing_notes:
        raise ValueError(f"Every slide needs a script. Missing on slides: {missing_notes}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    save(prs, str(output_path))
    print(f"[OK] Deck successfully built: {output_path} ({len(prs.slides)} slides)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the optional SKF presentation")
    parser.add_argument("--presentation-skill", default=os.environ.get("SKF_PRESENTATION_SKILL"),
                        help="Directory containing scripts/skf_deck.py and assets")
    parser.add_argument("--template", type=Path, help="Override the presentation template")
    parser.add_argument("--output", type=Path,
                        default=Path("artifacts") / "The Self-Hardening Agent Swarm.pptx")
    args = parser.parse_args()
    if not args.presentation_skill:
        parser.error("Provide --presentation-skill or SKF_PRESENTATION_SKILL for the optional deck builder")
    try:
        build_deck(args.output, Path(args.presentation_skill), args.template)
    except (OSError, ImportError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
