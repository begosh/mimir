#!/usr/bin/env python3
"""Install one shared Mímir package and link each CLI's discovery location."""
from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SKILL_NAME = "mimir"
REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_FILES = ("SKILL.md", "README.md", "LEARNINGS.md", "requirements.txt", "requirements-workers.txt", "requirements-research.txt", "LICENSE", ".gitignore")
PACKAGE_DIRS = ("scripts", "prompts", "docs")


def shared_skill_path(project_dir: Path | None = None) -> Path:
    return (project_dir or Path.home()).absolute() / ".agents" / "skills" / SKILL_NAME


def get_global_targets() -> List[Tuple[str, Path]]:
    home = Path.home()
    targets = [
        ("Agent Skills (shared)", shared_skill_path()),
        ("OpenAI Codex CLI (compatibility)", home / ".codex/skills" / SKILL_NAME),
        ("Claude Code", home / ".claude/skills" / SKILL_NAME),
        ("Antigravity CLI", home / ".gemini/antigravity-cli/skills" / SKILL_NAME),
        ("Antigravity", home / ".gemini/antigravity/skills" / SKILL_NAME),
        ("OpenCode", Path(os.environ.get("OPENCODE_CONFIG_DIR") or str(
            Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))) / "opencode")) / "skills" / SKILL_NAME),
    ]
    legacy = home / ".gemini/config/skills" / SKILL_NAME
    if os.path.lexists(legacy):
        targets.append(("Antigravity (legacy compatibility)", legacy))
    return targets


def get_project_targets(project_dir: Path) -> List[Tuple[str, Path]]:
    project_dir = project_dir.absolute()
    return [
        ("Project Agent Skills (shared)", shared_skill_path(project_dir)),
        ("Project Codex Skills (compatibility)", project_dir / ".codex/skills" / SKILL_NAME),
        ("Project Claude Skills", project_dir / ".claude/skills" / SKILL_NAME),
        ("Project OpenCode Skills (compatibility)", project_dir / ".opencode/skills" / SKILL_NAME),
    ]


def _is_link(path: Path) -> bool:
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        return True
    if os.name == "nt" and os.path.lexists(path):
        return bool(getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    return False


def _validate_destination(path: Path) -> Path:
    path = path.absolute()
    # Resolve the parent separately: replacing a junction must never replace
    # its target. Only the explicitly named skill directory may be moved.
    if path.name != SKILL_NAME or path.parent.name != "skills":
        raise ValueError(f"Expected a skills/{SKILL_NAME} destination: {path}")
    if _is_link(path.parent):
        raise ValueError(f"Skill discovery directory must not be a link: {path.parent}")
    return path.parent.resolve() / path.name


def _backup_path(destination: Path, backup_root: Path | None = None) -> Path:
    if backup_root is None:
        scope = next((p.parent for p in destination.parents if p.name == ".agents"), Path.home())
        backup_root = scope / ".agents" / "mimir-install-backups"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return backup_root.absolute() / f"{stamp}-{uuid.uuid4().hex[:8]}" / destination.parent.parent.name / SKILL_NAME


def _create_directory_link(source: Path, destination: Path) -> None:
    if os.name != "nt":
        os.symlink(str(source), str(destination), target_is_directory=True)
        return
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise RuntimeError("PowerShell is required to create Windows directory junctions.")
    env = os.environ.copy()
    env["MIMIR_LINK_SOURCE"] = str(source)
    env["MIMIR_LINK_DESTINATION"] = str(destination)
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    result = subprocess.run(
        [shell, "-NoProfile", "-NonInteractive", "-Command",
         "$ErrorActionPreference = 'Stop'; New-Item -ItemType Junction "
         "-Path $env:MIMIR_LINK_DESTINATION -Target $env:MIMIR_LINK_SOURCE | Out-Null"],
        env=env, capture_output=True, text=True, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW, startupinfo=startup,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Could not create directory junction")


def link_skill_tree(source: Path, destination: Path, backup_root: Path | None = None) -> Path | None:
    """Replace a copy with a verified link, preserving it outside discovery."""
    source = source.resolve(strict=True)
    destination = _validate_destination(destination)
    if destination.exists() and destination.resolve() == source:
        return None
    if destination == source or destination in source.parents:
        raise ValueError("A skill link cannot contain its source directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f".mimir-link-{uuid.uuid4().hex}"
    backup = None
    try:
        _create_directory_link(source, staging)
        if staging.resolve() != source or not (staging / "SKILL.md").is_file():
            raise RuntimeError("Skill directory link verification failed")
        if os.path.lexists(destination):
            backup = _backup_path(destination, backup_root)
            backup.parent.mkdir(parents=True, exist_ok=True)
            # Absolute destination was checked above; os.replace moves the
            # junction itself on Windows, never anything in its target.
            os.replace(destination, backup)
        try:
            os.replace(staging, destination)
        except OSError:
            if backup is not None:
                os.replace(backup, destination)
            raise
        return backup
    finally:
        if os.path.lexists(staging):
            if staging.is_symlink():
                staging.unlink()
            else:
                staging.rmdir()  # removes a junction, never its target


def _replace_package(source: Path, destination: Path) -> None:
    """Retry temporary Windows deny-delete handles without widening targets."""
    for attempt in range(5):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if os.name != "nt" or attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))


def copy_skill_tree(src: Path, dst: Path, use_link: bool = False,
                    backup_root: Path | None = None) -> Path | None:
    """Stage a clean package, preserve notes and restore the old copy on failure."""
    src = src.resolve(strict=True)
    dst = _validate_destination(dst)
    if not (src / "SKILL.md").is_file():
        raise ValueError(f"Source has no SKILL.md: {src}")
    if use_link:
        return link_skill_tree(src, dst, backup_root)
    if dst.exists() and dst.resolve() == src and not _is_link(dst):
        return
    if dst in src.parents:
        raise ValueError("The installed package cannot contain its source")
    for name in (*PACKAGE_FILES, *PACKAGE_DIRS):
        source_entry = src / name
        entries = [source_entry]
        if source_entry.is_dir() and not _is_link(source_entry):
            entries.extend(source_entry.rglob("*"))
        if any(_is_link(entry) for entry in entries):
            raise ValueError(f"Package resources must not contain links: {source_entry}")
    # Read notes through an existing top-level developer link deliberately,
    # but never through a nested link that could point at unrelated user files.
    existing_notes = dst / "LEARNINGS.md"
    if _is_link(existing_notes):
        raise ValueError(f"Learning file must not be a link: {existing_notes}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    staging = dst.parent / f".mimir-copy-{uuid.uuid4().hex}"
    backup = None
    try:
        staging.mkdir()
        for name in PACKAGE_FILES:
            resource = existing_notes if name == "LEARNINGS.md" and existing_notes.is_file() else src / name
            if resource.is_file():
                shutil.copy2(resource, staging / name)
        for name in PACKAGE_DIRS:
            if (src / name).is_dir():
                shutil.copytree(src / name, staging / name,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        if os.path.lexists(dst):
            backup = _backup_path(dst, backup_root)
            backup.parent.mkdir(parents=True, exist_ok=True)
            os.replace(dst, backup)
        try:
            _replace_package(staging, dst)
        except OSError:
            if backup is not None:
                os.replace(backup, dst)
            raise
    finally:
        if staging.exists():
            # Verify the absolute staging target before any recursive deletion.
            if _is_link(staging) or staging.resolve().parent != dst.parent.resolve():
                raise ValueError(f"Unsafe package staging cleanup path: {staging}")
            shutil.rmtree(staging)
    return backup


def install_shared_skill(src: Path, targets: List[Tuple[str, Path]], canonical: Path,
                         use_link: bool = False, backup_root: Path | None = None) -> List[Tuple[Path, Path]]:
    canonical_backup = copy_skill_tree(src, canonical, use_link=use_link, backup_root=backup_root)
    print(f"[OK] Shared Mímir package: {canonical}")
    if canonical_backup:
        print(f"  Previous shared package preserved: {canonical_backup}")
    backups = []
    for name, destination in targets:
        if destination.absolute() == canonical.absolute():
            continue
        backup = link_skill_tree(canonical, destination, backup_root)
        if backup:
            backups.append((destination, backup))
            print(f"  Previous installation preserved: {backup}")
        print(f"[OK] {name}: {destination} -> {canonical}")
    return backups


def install_dependencies(workers: bool = False, research: bool = False) -> bool:
    requirements = REPO_ROOT / ("requirements-research.txt" if research else "requirements-workers.txt" if workers else "requirements.txt")
    if not requirements.exists():
        return True
    return subprocess.call([sys.executable, "-m", "pip", "install", "-r", str(requirements)]) == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Install one shared Mímir package with CLI directory links")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--global", "-g", action="store_true", help="Install globally (default)")
    scope.add_argument("--project", "-p", nargs="?", const=".", help="Install into a project")
    parser.add_argument("--target", "-t", choices=["all", "codex", "antigravity", "claude", "opencode", "agents"],
                        default="all", help="Choose CLI links; the shared package is always installed")
    parser.add_argument("--link", "-l", action="store_true",
                        help="Developer mode: also link the shared package to this source checkout")
    parser.add_argument("--workers", action="store_true", help="Install SDK/server and MCP dependencies (default)")
    parser.add_argument("--base-only", action="store_true", help="Install base dependencies only for explicitly selected legacy/HTTP workers")
    parser.add_argument("--research", action="store_true", help="Install pinned optional DSPy, GEPA and Deno research dependencies")
    parser.add_argument("--skip-pip", action="store_true", help="Skip Python dependency installation")
    args = parser.parse_args()
    project = Path(args.project).resolve() if args.project is not None else None
    canonical = shared_skill_path(project)
    entries = get_project_targets(project) if project else get_global_targets()
    if args.target != "all":
        word = "agent skills" if args.target == "agents" else args.target
        entries = [entry for entry in entries if word in entry[0].lower()]
    try:
        if not entries:
            raise ValueError(
                f"Target '{args.target}' is unsupported for project installation. "
                "Choose agents, codex, claude or opencode, or install this target globally."
            )
        if not args.skip_pip and not install_dependencies(workers=not args.base_only, research=args.research):
            raise RuntimeError("Python dependency installation failed")
        install_shared_skill(REPO_ROOT, entries, canonical, use_link=args.link,
                             backup_root=(project / ".mimir/install-backups") if project else None)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"[FAIL] Mímir installation: {exc}", file=sys.stderr)
        return 1
    print("[OK] Installation complete. Restart your CLI session to refresh skill discovery.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
