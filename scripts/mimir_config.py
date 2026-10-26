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
HTTP_BACKENDS = ("responses", "openai", "anthropic", "ollama")
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
    if backend == "opencode" and "/" in model and not all(model.split("/", 1)):
        raise ConfigurationRequired("OpenCode provider/model cannot have an empty component.")
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


def configure(backend: Optional[str] = None, model: Optional[str] = None, effort: Optional[str] = None,
              path: Optional[Path] = None) -> dict:
    """Save an explicitly agreed profile atomically. Allows partial updates when a profile exists."""
    target = path or config_path()
    existing = None
    if target.exists():
        try:
            existing = load_config(target)
        except ConfigurationRequired:
            existing = None

    effective_backend = backend or (existing["backend"] if existing else None)
    if not effective_backend:
        raise ConfigurationRequired(
            "Choose an explicit backend (e.g. codex, agy, claude, responses) before saving setup."
        )

    same_backend = existing and (backend is None or backend == existing["backend"])
    effective_model = model or (existing["model"] if same_backend else None) or DEFAULT_MODELS.get(effective_backend)
    effective_effort = effort or (existing["effort"] if same_backend else None) or "low"

    data = validate({"version": 1, "backend": effective_backend,
                     "model": effective_model, "effort": effective_effort})
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


def format_config_view(path: Optional[Path] = None, host: Optional[str] = None,
                       host_model: Optional[str] = None) -> str:
    """Return a clean human-readable representation of project configuration."""
    status = config_status(host=host, path=path, host_model=host_model)
    target = status["config_path"]
    configured = status["configured"]
    settings = status["settings"] or {}

    lines = [
        "M Í M I R // Project Configuration",
        "═" * 60,
        f"Location: {target} (Status: {'Configured' if configured else 'Not Configured'})",
        "",
    ]
    if configured:
        lines.extend([
            f"  backend : {settings.get('backend')}",
            f"  model   : {settings.get('model')}",
            f"  effort  : {settings.get('effort')}",
            "",
            "To modify settings:",
            "  mimir config --model <model>",
            "  mimir config --backend <backend> --model <model> --effort <effort>",
            "  mimir config model=<model>",
        ])
    else:
        lines.extend([
            "No project configuration saved for this workspace.",
            f"  Suggested backend : {status.get('suggested_backend') or 'codex'}",
            f"  Suggested model   : {status.get('suggested_model') or 'gpt-6.1-sol'}",
            f"  Suggested effort  : {status.get('suggested_effort') or 'low'}",
            "",
            "To save configuration:",
            "  mimir config --backend codex --model gpt-6.1-sol --effort low",
        ])
    lines.append("═" * 60)
    return "\n".join(lines)


def format_status_view(backend: Optional[str] = None, model: Optional[str] = None,
                       effort: Optional[str] = None, path: Optional[Path] = None,
                       workspace: Optional[Path] = None, check_search: bool = False) -> str:
    """Return a formatted terminal dashboard of active configuration, environment, and readiness."""
    from diagnostics import collect_diagnostics

    ws = Path(workspace or Path.cwd()).resolve()
    target = path or config_path(ws)
    try:
        resolved_backend, resolved_model, resolved_effort = resolve_execution(backend, model, effort, target)
    except ConfigurationRequired:
        resolved_backend = backend or "codex"
        resolved_model = model
        resolved_effort = effort

    diag = collect_diagnostics(
        backend=resolved_backend,
        model=resolved_model,
        effort=resolved_effort,
        workspace=ws,
        check_search=check_search
    )

    ready_str = "YES - Ready for execution" if diag.get("ready") else "NO - Prerequisites missing"
    native = diag.get("native", {})
    text_api = diag.get("text_api", {})

    lines = [
        "M Í M I R // System Status & Configuration",
        "═" * 64,
        f"Workspace:       {diag.get('workspace')}",
        f"Config File:     {target} ({'Saved' if target.exists() else 'Using Environment/Defaults'})",
        "",
        "[Active Execution Profile]",
        f"  Backend:       {diag.get('backend')} ({diag.get('worker_transport')})",
        f"  Worker Model:  {diag.get('model') or '[None set - will require model]'}",
        f"  Effort:        {diag.get('effort') or 'low'}",
        f"  Transport:     {diag.get('worker_transport')} (Direct text API + lazy native tools)",
        "",
        "[Environment & Readiness]",
        f"  Ready:         {ready_str}",
        f"  API Provider:  {text_api.get('provider') or native.get('provider') or 'native'}",
    ]

    for env_item in native.get("required_environment", []):
        env_name = env_item.get("name")
        source = env_item.get("source") or ("Missing" if not env_item.get("available") else "Available")
        lines.append(f"  Auth Credential: {env_name} [{source}]")

    lines.extend([
        "",
        "[Storage & Memory]",
        f"  Run Storage:   {diag.get('run_root')}",
        f"  Curated Bank:  {diag.get('memory', {}).get('guidance_path')} (mode: {diag.get('memory', {}).get('mode')})",
        "",
        "[Harness & Installation]",
        f"  Python:        {diag.get('python_version')} ({diag.get('interpreter')})",
        f"  Global Skill:  {'Mounted & Verified' if diag.get('installation_matches_runtime') else 'Local/Unlinked'}",
    ])

    if diag.get("errors"):
        lines.extend([
            "",
            "[Errors / Blockers]",
            *(f"  ! {err}" for err in diag["errors"])
        ])

    lines.append("═" * 64)
    return "\n".join(lines)


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
            "default_text_transport": "responses", "default_tool_transport": "native",
            "note": "New tool-runtime runs use direct text API calls; API credentials and explicit API model ID required. CLI discovery verifies neither access route."}


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
