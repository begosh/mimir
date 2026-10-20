"""
scripts/clean_backend_sessions.py
Cleans up orphaned Mímir / AgySwarm backend micro-agent sessions from
~/.gemini/antigravity-cli so they do not pollute /resume or take up disk space.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
from pathlib import Path


def get_backend_conversation_ids(db_path: Path, brain_base: Path):
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return [], []

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT conversation_id, title, preview, last_modified_time FROM conversation_summaries ORDER BY last_modified_time DESC;"
    ).fetchall()

    backend_ids = []
    user_ids = []

    for cid, title, preview, mtime in rows:
        t_path = brain_base / cid / ".system_generated" / "logs" / "transcript.jsonl"
        is_backend = False

        text = (title + " " + (preview or "")).lower()
        if "mikro-agent" in text or "mikroagent" in text:
            is_backend = True
        elif t_path.exists():
            try:
                with open(t_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(2048)
                    if "mikro-agent" in content or "mikroagent" in content:
                        is_backend = True
            except Exception:
                pass

        if is_backend:
            backend_ids.append((cid, title, mtime))
        else:
            user_ids.append((cid, title, mtime))

    conn.close()
    return backend_ids, user_ids


def purge_sessions(apply: bool = False):
    cli_base = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".gemini" / "antigravity-cli"
    db_path = cli_base / "conversation_summaries.db"
    brain_base = cli_base / "brain"
    proto_path = cli_base / "jetbox_summaries_proto.pb"

    backend_ids, user_ids = get_backend_conversation_ids(db_path, brain_base)

    print(f"=== Antigravity Conversation Inspector ===")
    print(f"Preserved user sessions: {len(user_ids)}")
    print(f"Backend micro-agent sessions to clean: {len(backend_ids)}")

    total_bytes = 0
    for cid, _, _ in backend_ids:
        cdir = brain_base / cid
        if cdir.exists():
            for root, _, files in os.walk(cdir):
                for file in files:
                    try:
                        total_bytes += os.path.getsize(os.path.join(root, file))
                    except Exception:
                        pass

    print(f"Disk space occupied in brain/: {total_bytes / (1024 * 1024):.2f} MB")

    if not apply:
        print("\n[DRY RUN] Inga ändringar genomfördes. Kör med --apply för att rensa.")
        return

    print("\nUtför rensning...")
    conn = sqlite3.connect(db_path)
    with conn:
        for cid, _, _ in backend_ids:
            conn.execute("DELETE FROM conversation_summaries WHERE conversation_id = ?;", (cid,))
    conn.close()
    print(f"[OK] Raderade {len(backend_ids)} poster från conversation_summaries.db")

    cleaned_dirs = 0
    for cid, _, _ in backend_ids:
        cdir = brain_base / cid
        if cdir.exists():
            shutil.rmtree(cdir, ignore_errors=True)
            cleaned_dirs += 1

        conv_file = cli_base / "conversations" / f"{cid}.db"
        if conv_file.exists():
            try:
                conv_file.unlink()
            except Exception:
                pass

        annot_file = cli_base / "annotations" / f"{cid}.pbtxt"
        if annot_file.exists():
            try:
                annot_file.unlink()
            except Exception:
                pass

    print(f"[OK] Tog bort {cleaned_dirs} mappar från {brain_base}")

    # Remove proto cache so agy reconstructs it purely from legitimate sessions
    if proto_path.exists():
        try:
            proto_path.unlink()
            print(f"[OK] Återställde jetbox_summaries_proto.pb för automatisk ombyggnad.")
        except Exception as e:
            print(f"[VARNING] Kunde inte ta bort proto-cache: {e}")

    print(f"\nKlart! {len(user_ids)} användarsessioner är bevarade. /resume är nu helt ren från backend-anrop.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean up Mímir backend sessions from Antigravity CLI.")
    parser.add_argument("--apply", action="store_true", help="Genomför borttagningen.")
    args = parser.parse_args()
    purge_sessions(apply=args.apply)
