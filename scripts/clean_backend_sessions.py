"""
scripts/clean_backend_sessions.py
Read-only inspector for legacy Antigravity sessions. The current engine
produces no ownership manifest for them, so deletion is disabled.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def get_backend_conversation_ids(db_path: Path, brain_base: Path):
    """Return no owned sessions until a trustworthy ownership protocol exists."""
    if not db_path.is_file():
        print(f"Database not found at {db_path}")
        return [], []

    # Titles and prompts are user content, not ownership proof. Inspection must
    # not create a database, inspect arbitrary session paths or change journals.
    conn = sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT conversation_id, title, last_modified_time "
            "FROM conversation_summaries ORDER BY last_modified_time DESC"
        ).fetchall()
    finally:
        conn.close()
    return [], rows


def purge_sessions(apply: bool = False):
    if apply:
        raise RuntimeError(
            "Deletion disabled: legacy sessions have no Mímir ownership proof. "
            "Titles, previews and transcript keywords cannot authorize deletion. "
            "Use the owning CLI's session management controls."
        )
    cli_base = Path.home() / ".gemini" / "antigravity-cli"
    _, unowned = get_backend_conversation_ids(
        cli_base / "conversation_summaries.db", cli_base / "brain"
    )
    print("=== Antigravity Conversation Inspector ===")
    print(f"Sessions without Mímir ownership proof: {len(unowned)}")
    print("[READ ONLY] No sessions, files, databases or shared caches were changed.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect legacy Antigravity sessions safely")
    parser.add_argument("--apply", action="store_true", help="Disabled without ownership proof")
    args = parser.parse_args()
    try:
        purge_sessions(apply=args.apply)
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
