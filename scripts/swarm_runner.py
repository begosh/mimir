"""
scripts/swarm_runner.py
CLI entrypoint forwarding directly into M Í M I R.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from mimir import run_mimir


def main():
    parser = argparse.ArgumentParser(description="M Í M I R // Swarm Runner")
    parser.add_argument("question", type=str, help="Den komplexa frågan, strategin eller optimeringsmålet.")
    parser.add_argument("--output", "-o", type=str, default="artifacts/mimir_artifact.json", help="Utdatasökväg för rapporten.")
    parser.add_argument("--backend", "-b", type=str, default=None, choices=["auto", "agy", "codex", "claude", "opencode", "openai", "anthropic", "ollama"], help="Backend override; otherwise use saved project profile")
    parser.add_argument("--effort", default=None, help="Worker effort or OpenCode variant")
    parser.add_argument("--worker-timeout", type=float, default=180, help="Timeout per CLI call in seconds")
    parser.add_argument("--concurrency", type=int, default=4, help="Maximum concurrent workers")
    parser.add_argument("--progress", choices=["terminal", "jsonl"], default="terminal", help="Progress display format")
    parser.add_argument("--model", "-m", type=str, default=None, help="Modell för mikromodeller.")
    parser.add_argument("--skip-web", action="store_true", help="Hoppa över omvärldsspaning.")
    parser.add_argument("--depth", type=int, default=2, help="Max rekursionsdjup.")
    parser.add_argument("--sources", "-s", type=str, default=None, help="Kommaseparerad lista med specifika källdomäner.")
    parser.add_argument("--no-jev", action="store_true", help="Inaktivera JEV-optimering.")

    args = parser.parse_args()
    source_list = [s.strip() for s in args.sources.split(",")] if args.sources else None

    out_path = Path(args.output)
    md_path = str(out_path.with_suffix(".md")) if out_path.suffix == ".json" else str(out_path)

    asyncio.run(run_mimir(
        goal=args.question,
        output_path=md_path,
        backend=args.backend,
        model=args.model,
        skip_web=args.skip_web,
        max_depth=args.depth,
        sources=source_list,
        enable_jev=not args.no_jev,
        effort=args.effort,
        worker_timeout=args.worker_timeout,
        max_concurrency=args.concurrency,
        progress_format=args.progress,
    ))


if __name__ == "__main__":
    main()
