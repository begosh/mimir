"""Project execution preferences shared by every installed copy of Mimir.

No credentials or conversation state are stored here. The host asks the user
before calling configure; explicitly selected backends can also be used once.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

CLI_BACKENDS = ("agy", "codex", "claude", "opencode")
HTTP_BACKENDS = ("openai", "anthropic", "ollama")
BACKENDS = CLI_BACKENDS + HTTP_BACKENDS
DEFAULT_MODELS = {"agy": "gemini-3.8-flash-low", "claude": "haiku",
                  "openai": "gpt-4o-mini", "anthropic": "claude-3-5-haiku-20241022"}


def is_english_text(text: str) -> bool:
    """English is the universal standard across all Mímir pipelines."""
    return True


class ConfigurationRequired(ValueError):
    pass


def config_path(start: Optional[Path] = None) -> Path:
    project = (start or Path.cwd()).resolve()
    for parent in (project, *project.parents):
        if (parent / ".git").exists():
            project = parent
            break
    return project / ".mimir" / "config.json"


def validate(data: Any) -> dict:
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
        raise ConfigurationRequired("Unsupported Mimir configuration; run setup again.")
    if set(data) != {"version", "backend", "model", "effort"}:
        raise ConfigurationRequired("Mimir configuration accepts only backend, model, effort and version; never credentials.")
    backend, model, effort = data["backend"], data["model"], data["effort"]
    if not isinstance(backend, str) or backend not in BACKENDS:
        raise ConfigurationRequired("Unknown saved backend; choose a supported CLI or HTTP backend.")
    if not isinstance(model, str) or not model.strip() or len(model) > 200:
        raise ConfigurationRequired("Choose an explicit worker model before saving setup.")
    if backend == "opencode" and ("/" not in model or not all(model.split("/", 1))):
        raise ConfigurationRequired("OpenCode needs a provider/model.")
    if not isinstance(effort, str) or not effort or len(effort) > 100:
        raise ConfigurationRequired("Choose worker effort or an OpenCode variant.")
    if backend in CLI_BACKENDS[:3] and effort not in ("low", "medium", "high", "xhigh", "max"):
        raise ConfigurationRequired("CLI effort must be low, medium, high, xhigh, or max.")
    return data


def load_config(path: Optional[Path] = None) -> Optional[dict]:
    target = path or config_path()
    if not target.exists():
        return None
    try:
        return validate(json.loads(target.read_text(encoding="utf-8-sig")))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ConfigurationRequired(f"Cannot read Mimir configuration at {target}; repair it or run setup.") from None


def configure(backend: str, model: Optional[str] = None, effort: Optional[str] = None,
              path: Optional[Path] = None) -> dict:
    """Save an explicitly agreed profile atomically. Never discover a backend."""
    data = validate({"version": 1, "backend": backend,
                     "model": model or DEFAULT_MODELS.get(backend), "effort": effort or "low"})
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, target)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return data


def config_status(host: Optional[str] = None, path: Optional[Path] = None,
                  host_model: Optional[str] = None) -> dict:
    target = path or config_path()
    saved = load_config(target)
    available = [name for name in CLI_BACKENDS if shutil.which(name)]
    suggested = host if host in available else available[0] if len(available) == 1 else None
    suggested_model = DEFAULT_MODELS.get(suggested)
    if suggested == host and suggested in ("codex", "opencode"):
        suggested_model = host_model
    harness_mismatch = bool(saved and host and saved.get("backend") != host)
    return {"config_path": str(target), "configured": saved is not None,
            "harness_mismatch": harness_mismatch,
            "settings": saved, "available_clis": available,
            "suggested_backend": suggested, "confirmation_required": saved is None,
            "suggested_model": suggested_model, "suggested_effort": "low" if suggested else None,
            "note": "CLI discovery does not verify login, model availability or persistence."}


def resolve_execution(backend: Optional[str], model: Optional[str], effort: Optional[str],
                      path: Optional[Path] = None) -> tuple[str, Optional[str], Optional[str]]:
    """Explicit arguments > environment > saved project profile; no guessing."""
    requested = backend if backend and backend != "auto" else os.environ.get("MIMIR_BACKEND")
    if requested == "auto":
        requested = None
    saved = load_config(path) if not requested else None
    chosen = requested or (saved["backend"] if saved else None)
    if not chosen:
        raise ConfigurationRequired(
            "Choose CLI login reuse or HTTP access before running Mimir. "
            "Use --config-status, then --configure --backend <choice> --model <worker-model>, "
            "or pass --backend for this run only."
        )
    chosen = {"antigravity": "agy", "claude-code": "claude", "openai-codex": "codex"}.get(chosen, chosen)
    if chosen not in BACKENDS:
        raise ConfigurationRequired("Unknown selected backend; run setup or pass a supported --backend.")
    if saved is None:
        try:
            saved = load_config(path)
        except ConfigurationRequired:
            saved = None
    matching = saved if saved and saved["backend"] == chosen else {}
    selected_model = model or os.environ.get(f"MIMIR_{chosen.upper()}_MODEL") or os.environ.get("MIMIR_MODEL") or matching.get("model")
    selected_effort = effort or os.environ.get("MIMIR_EFFORT") or matching.get("effort")
    return chosen, selected_model, selected_effort
