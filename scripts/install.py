#!/usr/bin/env python3
"""
scripts/install.py
Universal Cross-Platform Installer for M Í M I R Agent Skill.
Installs Mímir into Codex CLI, Antigravity CLI, Claude Code, or Agent Skills (skills.sh)
either globally (~/.codex, ~/.gemini, ~/.agents) or project-locally (./.agents, ./.codex, etc.).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

# Ensure UTF-8 output even on legacy Windows code pages
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SKILL_NAME = "mimir"
REPO_ROOT = Path(__file__).resolve().parent.parent


def get_global_targets() -> List[Tuple[str, Path]]:
    home = Path.home()
    targets = []

    # 1. OpenAI Codex CLI
    codex_skills = home / ".codex" / "skills" / SKILL_NAME
    targets.append(("OpenAI Codex CLI", codex_skills))

    # 2. Google Antigravity CLI
    agy_skills = home / ".gemini" / "config" / "skills" / SKILL_NAME
    targets.append(("Antigravity CLI", agy_skills))

    # 3. Standard Agent Skills (skills.sh / agentskills.io)
    agent_skills = home / ".agents" / "skills" / SKILL_NAME
    targets.append(("Agent Skills (skills.sh)", agent_skills))

    # 4. Anthropic Claude Code
    claude_skills = home / ".claude" / "skills" / SKILL_NAME
    targets.append(("Claude Code", claude_skills))

    return targets


def get_project_targets(project_dir: Path) -> List[Tuple[str, Path]]:
    targets = [
        ("Project Agent Skills (.agents/skills)", project_dir / ".agents" / "skills" / SKILL_NAME),
        ("Project Codex Skills (.codex/skills)", project_dir / ".codex" / "skills" / SKILL_NAME),
    ]
    return targets


def copy_skill_tree(src: Path, dst: Path, use_link: bool = False) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)

    if dst.exists():
        if dst.is_symlink() or (hasattr(dst, "is_junction") and dst.is_junction()):
            dst.unlink()
        else:
            shutil.rmtree(dst, ignore_errors=True)

    if use_link:
        try:
            # Try symlink or directory junction
            os.symlink(str(src), str(dst), target_is_directory=True)
            return
        except Exception:
            pass  # Fallback to copy

    dst.mkdir(parents=True, exist_ok=True)

    # Core files to copy
    copy_files = ["SKILL.md", "README.md", "LEARNINGS.md", "requirements.txt", "LICENSE", ".gitignore"]
    for f in copy_files:
        src_file = src / f
        if src_file.exists():
            shutil.copy2(src_file, dst / f)

    # Core directories to copy
    copy_dirs = ["scripts", "prompts"]
    for d in copy_dirs:
        src_d = src / d
        if src_d.exists():
            shutil.copytree(src_d, dst / d, dirs_exist_ok=True)


def install_dependencies() -> bool:
    req_file = REPO_ROOT / "requirements.txt"
    if not req_file.exists():
        return True

    print(f"[*] Installing Python dependencies from {req_file}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(req_file)])
        return True
    except subprocess.CalledProcessError as e:
        print(f"[!] Warning: pip install failed with exit code {e.returncode}.")
        print("    You can manually run: pip install -r requirements.txt")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="M Í M I R // Universal Agent Skill Installer (Codex, Antigravity, skills.sh)"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--global",
        "-g",
        dest="is_global",
        action="store_true",
        default=True,
        help="Install globally for all detected AI agents (Codex, Antigravity, Claude, etc.) (Default)",
    )
    group.add_argument(
        "--project",
        "-p",
        dest="project_dir",
        nargs="?",
        const=".",
        help="Install locally in target project directory (default: current directory)",
    )
    parser.add_argument(
        "--target",
        "-t",
        choices=["all", "codex", "antigravity", "claude", "agents"],
        default="all",
        help="Target specific agent platform (default: all)",
    )
    parser.add_argument(
        "--link",
        "-l",
        action="store_true",
        help="Create symlink/junction instead of copying files (developer mode)",
    )
    parser.add_argument(
        "--skip-pip",
        action="store_true",
        help="Skip automatic installation of Python requirements (rich, curl_cffi, beautifulsoup4)",
    )

    args = parser.parse_args()

    print("=================================================================")
    print("           M Í M I R // Agent Skill Installer                    ")
    print("=================================================================")
    print(f"Source repository: {REPO_ROOT}\n")

    # Install pip dependencies first unless skipped
    if not args.skip_pip:
        install_dependencies()
        print()

    target_entries: List[Tuple[str, Path]] = []

    if args.project_dir is not None:
        proj_path = Path(args.project_dir).resolve()
        print(f"[>] Target Mode: Project-local ({proj_path})")
        all_proj_targets = get_project_targets(proj_path)
        if args.target == "codex":
            target_entries = [t for t in all_proj_targets if "codex" in t[0].lower()]
        elif args.target in ("agents", "all"):
            target_entries = all_proj_targets
        else:
            target_entries = all_proj_targets
    else:
        print("[>] Target Mode: Global AI Agent Ecosystem")
        all_global_targets = get_global_targets()
        if args.target == "all":
            target_entries = all_global_targets
        elif args.target == "codex":
            target_entries = [t for t in all_global_targets if "codex" in t[0].lower()]
        elif args.target == "antigravity":
            target_entries = [t for t in all_global_targets if "antigravity" in t[0].lower()]
        elif args.target == "claude":
            target_entries = [t for t in all_global_targets if "claude" in t[0].lower()]
        elif args.target == "agents":
            target_entries = [t for t in all_global_targets if "skills.sh" in t[0].lower()]

    installed_count = 0
    for name, dest in target_entries:
        try:
            print(f" [+] Installing to {name} -> {dest} ...", end=" ")
            copy_skill_tree(REPO_ROOT, dest, use_link=args.link)
            print("[OK]")
            installed_count += 1
        except Exception as e:
            print(f"[FAIL] ({e})")

    print("\n=================================================================")
    print(f"[OK] Successfully installed Mímir in {installed_count} location(s)!")
    print("=================================================================")
    print("\nQuick verification:")
    print("  • Codex CLI:       codex exec 'mimir: summarize architecture'")
    print("  • Antigravity:     agy 'mimir: start analysis'")
    print("  • Standalone CLI:  python scripts/mimir.py \"Your research query\"\n")


if __name__ == "__main__":
    main()
