"""Inference-free installation and native-provider preflight.

Diagnostics expose presence and identities, never environment or configuration
values that may contain credentials. Native environment hydration is returned
as a private override for an owned child process; this module does not mutate
the host environment, saved profiles, or login state.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 remains supported.
    import tomli as tomllib
from typing import Any

from mimir_config import ConfigurationRequired

_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
_PACKAGES = {"openai-codex": "0.163.0", "claude-agent-sdk": "0.2.172",
             "httpx": "0.28.1", "jsonschema": "4.26.0", "mcp": "2.3.0"}


def _persistent_environment(name: str, scope: str) -> str | None:
    if os.name != "nt":
        return None
    try:
        import winreg
        hive, path = ((winreg.HKEY_CURRENT_USER, "Environment") if scope == "User"
                      else (winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"))
        with winreg.OpenKey(hive, path) as key:
            value, kind = winreg.QueryValueEx(key, name)
        return value if kind in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) and isinstance(value, str) else None
    except OSError:
        return None


def _native_codex_config(workspace: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    configured_home = os.environ.get("CODEX_HOME")
    try:
        codex_home = Path(configured_home) if configured_home else Path.home() / ".codex"
    except RuntimeError:
        return {}, [], ["Cannot determine Codex home; provide CODEX_HOME in the worker environment."]
    user_path = codex_home / "config.toml"
    data: dict[str, Any] = {}
    paths: list[str] = []
    errors: list[str] = []
    ancestry = [*reversed(workspace.parents), workspace]
    for target in (user_path, *(parent / ".codex" / "config.toml" for parent in ancestry)):
        if target == user_path and str(target) in paths:
            continue
        if not target.exists():
            continue
        if target != user_path:
            projects = data.get("projects", {})
            trusted_root = next((parent for parent in [workspace, *workspace.parents]
                          if isinstance(projects.get(str(parent)), dict) and
                          projects[str(parent)].get("trust_level") == "trusted"), None) if isinstance(projects, dict) else None
            repository_root = next((parent for parent in [workspace, *workspace.parents]
                                    if (parent / ".git").exists()), None)
            project_root = repository_root or trusted_root
            if trusted_root is None or project_root is None or not target.parent.parent.is_relative_to(project_root):
                continue
        paths.append(str(target))
        try:
            layer = tomllib.loads(target.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError):
            errors.append("Cannot parse native Codex configuration; repair its TOML before running.")
            continue
        def merge(destination: dict, source: dict) -> None:
            for key, value in source.items():
                if isinstance(value, dict) and isinstance(destination.get(key), dict):
                    merge(destination[key], value)
                else:
                    destination[key] = value
        merge(data, layer)
    return data, paths, errors


def native_environment(backend: str, *, workspace: str | Path | None = None
                       ) -> tuple[dict[str, Any], dict[str, str]]:
    """Return public presence information and private child-only overrides.

    An explicitly empty Process value suppresses persisted-scope hydration.
    Only an environment variable actually required by the selected native
    Codex provider is considered. Other harnesses keep their native auth flow.
    """
    workspace = Path(workspace or Path.cwd()).resolve()
    report: dict[str, Any] = {"backend": backend, "provider": None,
                              "config_paths": [], "required_environment": [],
                              "missing_environment": [], "errors": [],
                              "authentication_verified": False,
                              "configuration_resolution": "static preflight; runtime owns final configuration"}
    required: list[str] = []
    if backend == "codex":
        config, paths, errors = _native_codex_config(workspace)
        report.update(config_paths=paths, errors=errors)
        provider = config.get("model_provider", "openai")
        if not isinstance(provider, str):
            report["errors"].append("Native Codex model_provider must be a string.")
            provider = "unknown"
        report["provider"] = provider
        providers = config.get("model_providers", {})
        settings = providers.get(provider, {}) if isinstance(providers, dict) else {}
        if isinstance(settings, dict):
            env_key = settings.get("env_key")
            if env_key is not None:
                required.append(env_key)
            headers = settings.get("env_http_headers", {})
            if isinstance(headers, dict):
                required.extend(headers.values())
    elif backend in ("openai", "anthropic"):
        required = ["OPENAI_API_KEY" if backend == "openai" else "ANTHROPIC_API_KEY"]
    overrides: dict[str, str] = {}
    for name in dict.fromkeys(item for item in required if isinstance(item, str)):
        if not _ENV_NAME.fullmatch(name):
            report["errors"].append("Native provider references an invalid environment variable name.")
            continue
        process_present = name in os.environ
        process = os.environ.get(name)
        user = _persistent_environment(name, "User")
        machine = _persistent_environment(name, "Machine")
        source = "Process" if process else None
        if not process_present and backend == "codex":
            if user:
                overrides[name] = user
                source = "User"
            elif machine:
                overrides[name] = machine
                source = "Machine"
        available = bool(process or name in overrides)
        report["required_environment"].append({"name": name,
            "process_present": process_present, "process_nonempty": bool(process),
            "user_present": bool(user), "machine_present": bool(machine),
            "source": source, "available": available,
            "child_override": name in overrides})
        if not available:
            report["missing_environment"].append(name)
    if any(not isinstance(item, str) for item in required):
        report["errors"].append("Native provider environment variable references must be strings.")
    report["ready"] = not report["errors"] and not report["missing_environment"]
    return report, overrides


def _code_identity(root: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    for relative in [Path("SKILL.md"), Path("requirements-research.txt"),
                     *sorted(p.relative_to(root) for p in (root / "scripts").rglob("*.py"))]:
        target = root / relative
        if target.is_file():
            digest.update(relative.as_posix().encode())
            digest.update(b"\0")
            digest.update(target.read_bytes())
            count += 1
    revision = None
    try:
        completed = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=3, check=False)
        candidate = completed.stdout.strip()
        if completed.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", candidate):
            revision = candidate
    except (OSError, subprocess.SubprocessError):
        pass
    return {"root": str(root), "content_sha256": digest.hexdigest(),
            "identity_files": count, "git_revision": revision}


def collect_diagnostics(backend: str, model: str | None = None, effort: str | None = None,
                        run_root: str | Path | None = None,
                        memory_path: str | Path | None = None, memory_mode: str = "read", *,
                        workspace: str | Path | None = None,
                        worker_transport: str | None = None, check_search: bool = False) -> dict[str, Any]:
    """Collect safe identities and prerequisites without starting any worker."""
    workspace = Path(workspace or Path.cwd()).resolve()
    worker_transport = worker_transport or os.environ.get("MIMIR_WORKER_TRANSPORT") or (
        "hybrid" if backend in {"codex", "agy", "claude", "opencode"} else "native")
    runtime_root = Path(__file__).resolve().parent.parent
    try:
        installed_root = Path.home() / ".agents" / "skills" / "mimir"
    except RuntimeError:
        installed_root = None
    packages = {}
    for package, expected in _PACKAGES.items():
        try:
            installed = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            installed = None
        packages[package] = {"installed": installed, "expected": expected,
                             "version_matches": installed == expected}
    native, _private = native_environment(backend, workspace=workspace)
    text_api = None
    if worker_transport == "hybrid" or backend == "responses":
        from text_api_backend import TextResponsesBackend
        try:
            adapter = TextResponsesBackend(model or "configuration_probe", effort=effort or "low")
            text_api = {"ready": True, "provider": adapter.provider, "model": model,
                        "effort": effort or "low", "verification": "Configuration only; no request made"}
        except (ValueError, OSError) as exc:
            text_api = {"ready": False, "errors": [str(exc)]}
    required = ({"codex": ["openai-codex", "jsonschema"],
                 "claude": ["claude-agent-sdk", "jsonschema"],
                 "opencode": ["httpx", "jsonschema"]}.get(backend, [])
                if worker_transport == "native" and backend != "responses" else ["httpx", "jsonschema"] if text_api is not None else [])
    missing_dependencies = [name for name in required if packages[name]["installed"] is None]
    cli = shutil.which(backend) if backend in ("codex", "claude", "opencode", "agy") else None
    needs_cli = worker_transport != "hybrid" and (backend == "agy" or backend == "opencode" or worker_transport == "cli")
    failures = list(text_api.get("errors", [])) if text_api is not None else list(native["errors"])
    if needs_cli and not cli:
        failures.append(f"Selected {backend} worker executable is unavailable.")
    memory = Path(memory_path).resolve() if memory_path else workspace / ".mimir" / "LEARNINGS.md"
    runtime = _code_identity(runtime_root)
    installed = _code_identity(installed_root) if installed_root and installed_root.is_dir() else None
    from research_program import research_runtime
    report = {"backend": backend, "model": model, "effort": effort,
        "worker_transport": worker_transport, "interpreter": sys.executable,
        "python_version": sys.version.split()[0], "workspace": str(workspace),
        "run_root": str(Path(run_root).resolve() if run_root else workspace / ".mimir" / "runs"),
        "runtime": runtime, "installed_skill": installed,
        "installation_matches_runtime": installed is not None and installed["content_sha256"] == runtime["content_sha256"],
        "dependencies": packages, "missing_dependencies": missing_dependencies,
        "optional_research": research_runtime(),
        "native": native, "worker_executable": cli,
        "text_api": text_api, "tool_runtime_preflight": "Deferred until tools are needed" if worker_transport == "hybrid" else "Required",
        "memory": {"mode": memory_mode, "guidance_path": str(memory),
                   "candidate_path": str(memory.parent / "learning-candidates.jsonl"),
                   "legacy_readonly_path": str(workspace / "LEARNINGS.md")},
        "research_tools": "Native configured catalog; read-only filesystem does not verify remote tool side effects",
        "errors": failures,
        "ready": (text_api["ready"] if text_api is not None else native["ready"]) and not missing_dependencies and not failures,
        "verification": "No inference, network authentication, tool invocation, or login mutation performed"}
    if check_search:
        from search_diagnostics import collect_search_diagnostics
        report["search"] = collect_search_diagnostics()
        report["verification"] = "Static worker preflight plus public search probes; no inference, login or configuration changes. Worker readiness and search usability are separate."
    else:
        report["search"] = {"checked": False, "reason": "Use --doctor or get_diagnostics(check_search=true) to test public search."}
    return report


def require_ready(report: dict[str, Any]) -> None:
    """Stop before planning when an established local prerequisite is missing."""
    if report.get("ready"):
        return
    native = report.get("text_api") or report.get("native", report)
    missing = native.get("missing_environment", [])
    dependencies = report.get("missing_dependencies", [])
    if missing:
        name = missing[0]
        raise ConfigurationRequired(
            f"Missing environment variable: {name}. Set it in the worker process or Windows User scope, "
            "then retry; Mimir does not start planning without the selected provider credential.")
    if dependencies:
        raise ConfigurationRequired("Missing worker dependencies: " + ", ".join(dependencies) +
                                    "; install requirements-workers.txt with the reported interpreter.")
    raise ConfigurationRequired("; ".join(report.get("errors") or native.get("errors") or
                                          ["Selected worker configuration is not ready."]))
