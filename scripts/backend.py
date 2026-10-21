"""
scripts/backend.py
Universal Multi-Backend Swarm Engine for M Í M I R.
Abstracts LLM execution across:
- Antigravity CLI (agy.exe) - Zero API keys, local authenticated session
- OpenAI Codex CLI (codex.exe) - Zero API keys, local authenticated session
- Claude Code CLI (claude) - Login reuse, native non-persistence
- OpenCode CLI (opencode) - Supported login reuse, disposable XDG storage
- OpenAI API & Compatible endpoints (Ollama, LMStudio, vLLM, OpenRouter)
- Anthropic Claude API (Claude 3.5 Haiku, Claude 3.7 Sonnet)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import signal
import tempfile
from contextlib import contextmanager
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union


@dataclass
class SwarmTask:
    role: str
    prompt: str
    model: Optional[str] = None
    effort: Optional[str] = None  # inherit the run's worker effort
    json_schema: Optional[Dict[str, Any]] = None
    input_data: Optional[Any] = None


@dataclass
class SwarmResult:
    role: str
    status: str  # "SUCCESS" | "ERROR"
    data: Any
    raw_response: str
    duration_seconds: float = 0.0
    tokens_used: int = 0


class BaseSwarmBackend(ABC):
    """Abstract base class for all Mímir LLM backends."""

    def __init__(self, default_model: str, max_concurrency: int = 4):
        if max_concurrency < 1:
            raise ValueError("Worker concurrency must be positive.")
        self.default_model = default_model
        self.default_effort = "low"
        self.timeout_seconds = 180
        self.semaphore = asyncio.Semaphore(max_concurrency)

    @abstractmethod
    async def spawn(
        self,
        prompt: str,
        role: str = "Micro-Worker",
        model: Optional[str] = None,
        effort: Optional[str] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        input_data: Optional[Any] = None,
    ) -> SwarmResult:
        """Spawns an isolated LLM micro-worker."""
        pass

    def cleanup(self) -> None:
        """Cleanup any temporary resources."""
        pass

    async def __aenter__(self) -> "BaseSwarmBackend":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.cleanup()

    async def parallel(self, tasks: List[SwarmTask]) -> List[SwarmResult]:
        """Executes multiple SwarmTasks concurrently."""
        coroutines = [
            self.spawn(
                prompt=t.prompt,
                role=t.role,
                model=t.model or self.default_model,
                effort=t.effort,
                json_schema=t.json_schema,
                input_data=t.input_data,
            )
            for t in tasks
        ]
        return await asyncio.gather(*coroutines)

    async def _run_cli(self, cmd: List[str], prompt: Optional[str] = None,
                       env: Optional[Dict[str, str]] = None) -> tuple[int, str, str]:
        """Bound each CLI call and reap it before releasing disposable storage."""
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdin=asyncio.subprocess.PIPE if prompt is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
            start_new_session=os.name != "nt",
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(prompt.encode("utf-8") if prompt is not None else None),
                timeout=getattr(self, "timeout_seconds", 180),
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            if proc.returncode is None:
                if os.name == "nt" and getattr(proc, "pid", None):
                    killer = await asyncio.create_subprocess_exec(
                        "taskkill", "/PID", str(proc.pid), "/T", "/F",
                        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                    )
                    await killer.wait()
                elif getattr(proc, "pid", None):
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    proc.kill()
            await proc.communicate()
            raise
        return proc.returncode, stdout.decode("utf-8", errors="replace").strip(), stderr.decode("utf-8", errors="replace").strip()

    async def check_cli(self) -> Dict[str, Any]:
        """Check flags without starting a model call or exposing credentials."""
        code, stdout, stderr = await self._run_cli(self.help_command)
        help_text = stdout + "\n" + stderr
        if code or not help_text.strip():
            raise RuntimeError(f"{self.__class__.__name__}: CLI help failed; repair the CLI installation.")
        missing = [flag for flag in self.required_flags if flag not in help_text]
        if missing:
            raise RuntimeError(f"CLI version is missing required flags: {', '.join(missing)}")
        self.cli_help = help_text
        return {
            "backend": self.__class__.__name__, "model": self.default_model,
            "effort": self.default_effort, "session_policy": self.session_policy,
            "timeout_seconds": self.timeout_seconds,
            "model_configured": self.default_model != "default",
        }

    @staticmethod
    def parse_json_from_text(raw_text: str) -> Any:
        """Robustly extracts JSON from raw LLM output."""
        if not raw_text or not raw_text.strip():
            return None

        # 1. Try direct parsing
        try:
            return json.loads(raw_text.strip())
        except Exception:
            pass

        # 2. Extract from markdown ```json ... ``` codeblocks
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text)
        if match:
            candidate = match.group(1).strip()
            try:
                return json.loads(candidate)
            except Exception:
                pass

        # 3. Search for outermost { ... } or [ ... ]
        first_brace = raw_text.find("{")
        last_brace = raw_text.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            candidate = raw_text[first_brace : last_brace + 1]
            try:
                return json.loads(candidate)
            except Exception:
                pass

        first_bracket = raw_text.find("[")
        last_bracket = raw_text.rfind("]")
        if first_bracket != -1 and last_bracket > first_bracket:
            candidate = raw_text[first_bracket : last_bracket + 1]
            try:
                return json.loads(candidate)
            except Exception:
                pass

        return raw_text.strip()

    async def execute_graph(
        self,
        graph: Any,  # TaskGraph
        blackboard: Optional[Any] = None,
        jev_gate: Optional[Any] = None,
        on_task_start: Optional[Callable[[Any], None]] = None,
        on_task_finish: Optional[Callable[[Any, SwarmResult, Optional[Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        Executes a TaskGraph using Kahn topological tiers, Blackboard state,
        and cryptographic EvidenceContracts.
        """
        import hashlib
        from task_graph import EvidenceContract, TaskStatus

        tiers = graph.get_execution_tiers()
        completed_data: Dict[str, Any] = {}

        for tier in tiers:
            tasks_to_run = []
            tier_nodes = []

            for node in tier:
                # Check for upstream failures
                has_failed_dep = any(
                    graph.nodes[d].status in (TaskStatus.FAILED, TaskStatus.CANCELLED)
                    for d in node.dependencies
                    if d in graph.nodes
                )
                if has_failed_dep:
                    node.status = TaskStatus.CANCELLED
                    continue

                if node.status == TaskStatus.PENDING:
                    all_deps_done = all(
                        graph.nodes[d].status == TaskStatus.COMPLETED
                        for d in node.dependencies
                        if d in graph.nodes
                    )
                    if all_deps_done:
                        node.status = TaskStatus.READY

                if node.status != TaskStatus.READY:
                    continue

                if jev_gate and hasattr(node, "jev_score") and node.jev_score < 0.25:
                    node.status = TaskStatus.CANCELLED
                    continue

                node_prompt = node.prompt
                if blackboard:
                    context_delta = blackboard.get_diff_since_last_sync(node.id)
                    if context_delta:
                        node_prompt += f"\n\n--- AKTUELL BLACKBOARD-KONTEXT ---\n{context_delta}\n--- SLUT KONTEXT ---"

                tasks_to_run.append(
                    SwarmTask(
                        role=node.role,
                        prompt=node_prompt,
                        model=getattr(node, "model", None) or self.default_model,
                        effort=None,
                    )
                )
                tier_nodes.append(node)
                node.status = TaskStatus.RUNNING
                if on_task_start:
                    on_task_start(node)

            if not tasks_to_run:
                continue

            results = await self.parallel(tasks_to_run)

            for node, res in zip(tier_nodes, results):
                if res.status == "SUCCESS":
                    node.status = TaskStatus.COMPLETED
                    raw_str = res.raw_response if isinstance(res.raw_response, str) else json.dumps(res.data)
                    raw_hash = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

                    contract = EvidenceContract(
                        grounding_ref=f"node://{node.id}",
                        raw_evidence_hash=raw_hash,
                        verification_passed=True,
                        assertion_notes=f"Körd via {self.__class__.__name__} på {res.duration_seconds:.2f}s",
                    )

                    if blackboard:
                        blackboard.commit_evidence(
                            node_id=node.id,
                            key=f"{node.id}_result",
                            value=res.data,
                            contract=contract,
                        )

                    completed_data[node.id] = {
                        "role": node.role,
                        "title": node.title,
                        "result": res.data,
                        "evidence_hash": raw_hash,
                        "duration": res.duration_seconds,
                    }

                    if on_task_finish:
                        on_task_finish(node, res, contract)
                else:
                    node.status = TaskStatus.FAILED
                    graph.cascade_failure(node.id)
                    if on_task_finish:
                        on_task_finish(node, res, None)

        return completed_data


@contextmanager
def disposable_cli_env(kind: str):
    """Keep CLI histories away from the user's home; copy only login material."""
    original_home = Path.home()
    with tempfile.TemporaryDirectory(prefix=f"mimir_{kind}_") as directory:
        root = Path(directory)
        env = os.environ.copy()
        env.update(HOME=str(root), USERPROFILE=str(root), TMP=str(root), TEMP=str(root), TMPDIR=str(root))
        for key, folder in (("XDG_DATA_HOME", "data"), ("XDG_STATE_HOME", "state"),
                            ("XDG_CACHE_HOME", "cache"), ("XDG_CONFIG_HOME", "config")):
            env[key] = str(root / folder)
            (root / folder).mkdir()
        if kind == "agy":
            destination = root / ".gemini"
            destination.mkdir()
            for name in ("oauth_creds.json", "google_accounts.json", "installation_id"):
                source = original_home / ".gemini" / name
                if source.exists():
                    shutil.copy2(source, destination / name)
            # Do not recursively expand this skill inside a micro-worker.
        elif kind == "opencode":
            source_data = Path(os.environ.get("XDG_DATA_HOME", str(original_home / ".local" / "share"))) / "opencode"
            destination = root / "data" / "opencode"
            destination.mkdir(parents=True)
            auth = source_data / "auth.json"
            if auth.exists():
                shutil.copy2(auth, destination / "auth.json")
            # Newer releases can store credentials in their DB. Do not copy that
            # DB: it also contains the user's conversations.
            env.pop("OPENCODE_CONFIG", None)
            env.pop("OPENCODE_CONFIG_CONTENT", None)
            env["OPENCODE_CONFIG_DIR"] = str(root / "config" / "opencode")
            env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
            env["OPENCODE_CONFIG_CONTENT"] = json.dumps({
                "share": "disabled", "autoupdate": False,
                "permission": {"*": "deny", "read": "allow", "glob": "allow", "grep": "allow", "webfetch": "allow"},
            })
        yield env


class AgySwarmBackend(BaseSwarmBackend):
    """
    Spawns headless agy.exe processes using the user's existing
    authenticated AGY CLI session. Uses the account's existing usage allowance.
    """

    def __init__(
        self,
        default_model: str = "gemini-3.8-flash-low",
        default_effort: str = "low",
        agy_path: Optional[str] = None,
        max_concurrency: int = 4,
        isolate_sessions: bool = True,
    ):
        super().__init__(default_model=default_model, max_concurrency=max_concurrency)
        self.default_effort = default_effort
        if not isolate_sessions:
            raise ValueError("Mimir AGY workers require disposable session storage.")

        resolved_path = agy_path or shutil.which("agy")
        if not resolved_path:
            # Common paths across OSes
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            candidates = [
                Path(local_appdata) / "agy" / "bin" / "agy.exe",
                Path.home() / ".local" / "bin" / "agy",
                Path("/usr/local/bin/agy"),
            ]
            for c in candidates:
                if c.exists():
                    resolved_path = str(c)
                    break

        if not resolved_path:
            raise FileNotFoundError(
                "Could not find 'agy' executable in PATH. "
                "Ensure Antigravity CLI is installed or configure an alternative backend."
            )
        self.agy_path = resolved_path
        self.timeout_seconds = 180
        self.help_command = [self.agy_path, "--help"]
        self.required_flags = ("--model", "--effort", "--output-format", "--sandbox", "--disable-slash-commands")
        self.session_policy = "disposable home per call (temporary session files removed)"

    async def spawn(
        self,
        prompt: str,
        role: str = "Micro-Worker",
        model: Optional[str] = None,
        effort: Optional[str] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        input_data: Optional[Any] = None,
    ) -> SwarmResult:
        async with self.semaphore:
            target_model = model or self.default_model
            target_effort = effort or self.default_effort

            full_prompt = prompt
            if input_data is not None:
                formatted_input = json.dumps(input_data, indent=2, ensure_ascii=False) if isinstance(input_data, (dict, list)) else str(input_data)
                full_prompt += f"\n\n--- INPUT DATA ---\n{formatted_input}\n--- END INPUT DATA ---"

            system_instruction = (
                f"You are a specialized micro-worker agent with role: '{role}'. "
                f"Solve the task objectively, concisely, and rigorously. Answer directly without preamble. "
                f"Do not launch Mimir or delegate this task. "
                f"Match the language of the prompt (respond in English if prompt is in English, in Swedish if in Swedish)."
            )

            cmd = [
                self.agy_path,
                "--model",
                target_model,
                "--effort",
                target_effort,
                "--output-format",
                "json",
                "--sandbox",
                "--disable-slash-commands",
            ]

            if json_schema:
                cmd.extend(["--json-schema", json.dumps(json_schema)])

            cmd.extend(["-p", f"{system_instruction}\n\n{full_prompt}"])

            start_time = asyncio.get_running_loop().time()
            try:
                with disposable_cli_env("agy") as sub_env:
                    code, raw_out, raw_err = await self._run_cli(cmd, env=sub_env)
            except (OSError, asyncio.TimeoutError) as exc:
                return SwarmResult(role, "ERROR", None, str(exc) or "Worker timed out")
            duration = asyncio.get_running_loop().time() - start_time

            if code != 0 or not raw_out:
                return SwarmResult(
                    role=role,
                    status="ERROR",
                    data=None,
                    raw_response=raw_err or raw_out,
                    duration_seconds=duration,
                )

            try:
                wrapper = json.loads(raw_out)
            except ValueError:
                return SwarmResult(role, "ERROR", None, "AGY returned malformed JSON")
            if isinstance(wrapper, dict) and (wrapper.get("is_error") or wrapper.get("error")):
                return SwarmResult(role, "ERROR", None, "AGY reported a worker error")
            parsed_data = self._parse_agy_output(raw_out)
            tokens = 0
            try:
                meta = json.loads(raw_out)
                tokens = meta.get("usage", {}).get("total_tokens", 0)
            except Exception:
                pass

            return SwarmResult(
                role=role,
                status="SUCCESS",
                data=parsed_data,
                raw_response=raw_out,
                duration_seconds=duration,
                tokens_used=tokens,
            )

    def _parse_agy_output(self, raw_out: str) -> Any:
        try:
            wrapper = json.loads(raw_out)
            if isinstance(wrapper, dict):
                candidates = [
                    wrapper.get("response"),
                    wrapper.get("result"),
                    wrapper.get("content"),
                    wrapper.get("text"),
                ]
                for c in candidates:
                    if c is not None:
                        if isinstance(c, (dict, list)):
                            return c
                        return self.parse_json_from_text(str(c))
                return wrapper
        except Exception:
            pass
        return self.parse_json_from_text(raw_out)


class CodexSwarmBackend(BaseSwarmBackend):
    """
    Spawns headless codex.exe processes using the user's existing
    authenticated Codex CLI session. Uses the account's existing usage allowance.
    """

    def __init__(
        self,
        default_model: Optional[str] = None,
        default_effort: str = "low",
        codex_path: Optional[str] = None,
        max_concurrency: int = 4,
    ):
        super().__init__(default_model=default_model or "default", max_concurrency=max_concurrency)
        self.default_effort = default_effort
        self.explicit_model = default_model

        resolved_path = codex_path
        if not resolved_path:
            # 1. Direct binary on Windows
            appdata = os.environ.get("APPDATA", "")
            direct_exe = (
                Path(appdata)
                / "npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe"
            )
            if direct_exe.exists():
                resolved_path = str(direct_exe)

        if not resolved_path:
            for name in ["codex.exe", "codex", "codex.cmd"]:
                w = shutil.which(name)
                if w:
                    resolved_path = w
                    break

        if not resolved_path:
            candidates = [
                Path.home() / ".local" / "bin" / "codex",
                Path("/usr/local/bin/codex"),
                Path.home() / "AppData" / "Roaming" / "npm" / "codex.cmd",
            ]
            for c in candidates:
                if c.exists():
                    resolved_path = str(c)
                    break

        if not resolved_path:
            raise FileNotFoundError(
                "Could not find 'codex' executable. "
                "Ensure OpenAI Codex CLI is installed or configure an alternative backend."
            )
        self.codex_path = resolved_path
        self.timeout_seconds = 180
        self.help_command = [self.codex_path, "exec", "--help"]
        self.required_flags = ("--ephemeral", "--output-schema", "--sandbox")
        self.session_policy = "native --ephemeral (no session rollout persistence)"

    async def check_cli(self) -> Dict[str, Any]:
        if self.default_model == "default":
            raise ValueError("Set an economical Codex worker model via --model or MIMIR_CODEX_MODEL.")
        return await super().check_cli()

    async def spawn(
        self,
        prompt: str,
        role: str = "Micro-Worker",
        model: Optional[str] = None,
        effort: Optional[str] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        input_data: Optional[Any] = None,
    ) -> SwarmResult:
        async with self.semaphore:
            target_model = model or self.explicit_model
            target_effort = effort or self.default_effort

            full_prompt = prompt
            if input_data is not None:
                formatted_input = (
                    json.dumps(input_data, indent=2, ensure_ascii=False)
                    if isinstance(input_data, (dict, list))
                    else str(input_data)
                )
                full_prompt += f"\n\n--- INPUT DATA ---\n{formatted_input}\n--- END INPUT DATA ---"

            system_instruction = (
                f"You are a specialized micro-worker agent with role: '{role}'. "
                f"Solve the task objectively, concisely, and rigorously. Answer directly without preamble. "
                f"Do not launch Mimir or delegate this task."
            )

            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f_out:
                out_file = f_out.name

            schema_file: Optional[str] = None
            if json_schema:
                with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8") as f_s:
                    json.dump(json_schema, f_s)
                    schema_file = f_s.name

            try:
                cmd = [
                    self.codex_path,
                    "exec",
                    "--ephemeral",
                    "--skip-git-repo-check",
                    "-s", "read-only",
                    "-o", out_file,
                ]

                if target_effort:
                    cmd.extend(["-c", f'model_reasoning_effort="{target_effort}"'])

                if target_model and target_model != "default":
                    cmd.extend(["-m", target_model])

                if schema_file:
                    cmd.extend(["--output-schema", schema_file])

                cmd.append("-")

                start_time = asyncio.get_event_loop().time()
                try:
                    code, raw_out, raw_err = await self._run_cli(cmd, prompt=f"{system_instruction}\n\n{full_prompt}")
                except (OSError, asyncio.TimeoutError) as exc:
                    return SwarmResult(role, "ERROR", None, str(exc) or "Worker timed out")
                duration = asyncio.get_event_loop().time() - start_time

                content = ""
                if os.path.exists(out_file):
                    try:
                        with open(out_file, "r", encoding="utf-8") as f:
                            content = f.read().strip()
                    except Exception:
                        pass

                if not content:
                    content = raw_out

                if code != 0 or not content:
                    return SwarmResult(
                        role=role,
                        status="ERROR",
                        data=None,
                        raw_response=raw_err or raw_out,
                        duration_seconds=duration,
                    )

                parsed_data = self.parse_json_from_text(content)

                # Parse tokens if reported in stdout
                tokens = 0
                match = re.search(r"tokens used\s*([\d,]+)", raw_out, re.IGNORECASE)
                if match:
                    try:
                        tokens = int(match.group(1).replace(",", ""))
                    except Exception:
                        pass

                return SwarmResult(
                    role=role,
                    status="SUCCESS",
                    data=parsed_data,
                    raw_response=content,
                    duration_seconds=duration,
                    tokens_used=tokens,
                )
            finally:
                if os.path.exists(out_file):
                    try:
                        os.remove(out_file)
                    except Exception:
                        pass
                if schema_file and os.path.exists(schema_file):
                    try:
                        os.remove(schema_file)
                    except Exception:
                        pass


class ClaudeCodeSwarmBackend(BaseSwarmBackend):
    """Authenticated Claude Code print calls, without resumable sessions."""

    def __init__(self, default_model: str = "haiku", default_effort: str = "low",
                 claude_path: Optional[str] = None, max_concurrency: int = 4):
        super().__init__(default_model, max_concurrency)
        self.claude_path = claude_path or shutil.which("claude")
        if not self.claude_path:
            raise FileNotFoundError("Could not find Claude Code ('claude') in PATH.")
        self.default_effort = default_effort
        self.timeout_seconds = 180
        self.help_command = [self.claude_path, "--help"]
        self.required_flags = ("--no-session-persistence", "--model", "--output-format", "--tools", "--strict-mcp-config", "--permission-mode", "--disable-slash-commands")
        self.session_policy = "native --no-session-persistence"
        self.cli_help = ""

    async def spawn(self, prompt: str, role: str = "Micro-Worker", model: Optional[str] = None,
                    effort: Optional[str] = None, json_schema: Optional[Dict[str, Any]] = None,
                    input_data: Optional[Any] = None) -> SwarmResult:
        async with self.semaphore:
            selected_model = model or self.default_model
            selected_effort = effort or self.default_effort
            cmd = [self.claude_path, "--print", "--no-session-persistence", "--output-format", "json",
                   "--model", selected_model, "--disable-slash-commands", "--strict-mcp-config",
                   "--tools", "Read,Glob,Grep,WebFetch,WebSearch", "--permission-mode", "dontAsk"]
            # Haiku does not expose adjustable reasoning effort. Older Claude
            # releases also lack the effort flag: never invent a flag or upgrade
            # the model merely to get effort controls.
            if "haiku" not in selected_model.lower():
                if "--effort" not in self.cli_help:
                    return SwarmResult(role, "ERROR", None, "This Claude CLI has no --effort control; use haiku or update it.")
                cmd.extend(["--effort", selected_effort])
            if json_schema:
                cmd.extend(["--json-schema", json.dumps(json_schema)])
            full_prompt = f"You are a Mimir micro-worker ({role}). Solve only this task. Do not launch Mimir or delegate.\n\n{prompt}"
            if input_data is not None:
                full_prompt += "\n\nINPUT DATA:\n" + json.dumps(input_data, ensure_ascii=False)
            start = asyncio.get_running_loop().time()
            try:
                code, stdout, stderr = await self._run_cli(cmd, prompt=full_prompt)
                wrapper = json.loads(stdout) if stdout else {}
                if code or not isinstance(wrapper, dict) or wrapper.get("is_error") or wrapper.get("subtype", "success") != "success":
                    return SwarmResult(role, "ERROR", None, stderr or stdout or "Empty Claude response")
                content = wrapper.get("structured_output", wrapper.get("result"))
                if content is None or content == "":
                    return SwarmResult(role, "ERROR", None, "Claude returned no result")
                raw = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
                usage = wrapper.get("usage", {})
                return SwarmResult(role, "SUCCESS", self.parse_json_from_text(raw), raw,
                                   asyncio.get_running_loop().time() - start,
                                   usage.get("input_tokens", 0) + usage.get("output_tokens", 0))
            except (OSError, ValueError, asyncio.TimeoutError) as exc:
                return SwarmResult(role, "ERROR", None, str(exc) or "Worker timed out")

    async def check_cli(self) -> Dict[str, Any]:
        info = await super().check_cli()
        if "haiku" in self.default_model.lower():
            info["effort"] = "not adjustable for Haiku; economical model selected"
        elif "--effort" not in self.cli_help:
            raise RuntimeError("This Claude CLI cannot set effort for this model; use haiku or update the CLI.")
        return info


class OpenCodeSwarmBackend(BaseSwarmBackend):
    """OpenCode JSON events with per-call disposable XDG storage.

    Supports reusable auth.json logins. DB-only credentials cannot be copied
    without bringing session history, so that storage format fails preflight.
    """

    def __init__(self, default_model: Optional[str] = None, default_effort: str = "low",
                 opencode_path: Optional[str] = None, max_concurrency: int = 4):
        if not default_model or "/" not in default_model:
            raise ValueError("OpenCode requires an explicit economical provider/model via --model or MIMIR_OPENCODE_MODEL.")
        super().__init__(default_model, max_concurrency)
        self.opencode_path = opencode_path or shutil.which("opencode")
        if not self.opencode_path:
            raise FileNotFoundError("Could not find 'opencode' in PATH.")
        self.default_effort = default_effort
        self.timeout_seconds = 180
        self.help_command = [self.opencode_path, "run", "--help"]
        self.required_flags = ("--model", "--format", "--variant")
        self.session_policy = "disposable XDG/home storage per call; no attach/resume/share"

    async def check_cli(self) -> Dict[str, Any]:
        info = await super().check_cli()
        auth = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "opencode" / "auth.json"
        if not auth.exists():
            raise RuntimeError("OpenCode needs reusable auth.json login storage; DB-only credentials are not yet supported without copying sessions.")
        info["effort"] = f"provider variant: {self.default_effort} (use 'none' for models without variants)"
        return info

    async def spawn(self, prompt: str, role: str = "Micro-Worker", model: Optional[str] = None,
                    effort: Optional[str] = None, json_schema: Optional[Dict[str, Any]] = None,
                    input_data: Optional[Any] = None) -> SwarmResult:
        async with self.semaphore:
            selected_effort = effort or self.default_effort
            cmd = [self.opencode_path, "run", "--format", "json", "--model", model or self.default_model]
            if selected_effort != "none":
                cmd.extend(["--variant", selected_effort])
            full_prompt = f"You are a Mimir micro-worker ({role}). Solve only this task. Do not launch Mimir or delegate.\n\n{prompt}"
            if input_data is not None:
                full_prompt += "\n\nINPUT DATA:\n" + json.dumps(input_data, ensure_ascii=False)
            if json_schema:
                full_prompt += "\nReturn JSON matching this schema:\n" + json.dumps(json_schema)
            start = asyncio.get_running_loop().time()
            try:
                with disposable_cli_env("opencode") as env:
                    code, stdout, stderr = await self._run_cli(cmd, prompt=full_prompt, env=env)
                events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
                errors = [event for event in events if event.get("type") == "error"]
                if code or errors:
                    return SwarmResult(role, "ERROR", None, stderr or json.dumps(errors) or stdout)
                raw = "\n".join(event.get("part", {}).get("text", "") for event in events if event.get("type") == "text").strip()
                if not raw:
                    return SwarmResult(role, "ERROR", None, "OpenCode returned no text result")
                tokens = 0
                for event in events:
                    if event.get("type") == "step_finish":
                        usage = event.get("part", {}).get("tokens", {})
                        tokens += usage.get("input", 0) + usage.get("output", 0)
                return SwarmResult(role, "SUCCESS", self.parse_json_from_text(raw), raw,
                                   asyncio.get_running_loop().time() - start, tokens)
            except (OSError, ValueError, asyncio.TimeoutError) as exc:
                return SwarmResult(role, "ERROR", None, str(exc) or "Worker timed out")


class OpenAISwarmBackend(BaseSwarmBackend):
    """
    Executes tasks using OpenAI API or OpenAI-compatible endpoints
    (Ollama, LMStudio, vLLM, OpenRouter) via standard Python library.
    Requires OPENAI_API_KEY (or local endpoint).
    """

    def __init__(
        self,
        default_model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        max_concurrency: int = 4,
    ):
        super().__init__(default_model=default_model, max_concurrency=max_concurrency)
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "dummy-key")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")

    async def spawn(
        self,
        prompt: str,
        role: str = "Micro-Worker",
        model: Optional[str] = None,
        effort: Optional[str] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        input_data: Optional[Any] = None,
    ) -> SwarmResult:
        async with self.semaphore:
            target_model = model or self.default_model

            full_prompt = prompt
            if input_data is not None:
                formatted_input = json.dumps(input_data, indent=2, ensure_ascii=False) if isinstance(input_data, (dict, list)) else str(input_data)
                full_prompt += f"\n\n--- INPUT DATA ---\n{formatted_input}\n--- END INPUT DATA ---"

            system_instruction = (
                f"You are a specialized micro-worker agent with the role: '{role}'. "
                f"Solve the task objectively, concisely, and rigorously. Answer directly without preamble."
            )

            payload: Dict[str, Any] = {
                "model": target_model,
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": full_prompt},
                ],
                "temperature": 0.2,
            }

            if json_schema:
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "output_schema", "schema": json_schema, "strict": True},
                }

            start_time = asyncio.get_event_loop().time()

            try:
                loop = asyncio.get_event_loop()
                data_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    f"{self.base_url}/chat/completions",
                    data=data_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                        "User-Agent": "Mimir-Swarm/2.0",
                    },
                    method="POST",
                )

                def _do_request():
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        return resp.read().decode("utf-8")

                resp_str = await loop.run_in_executor(None, _do_request)
                duration = asyncio.get_event_loop().time() - start_time

                resp_json = json.loads(resp_str)
                content = resp_json["choices"][0]["message"]["content"]
                tokens = resp_json.get("usage", {}).get("total_tokens", 0)

                parsed = self.parse_json_from_text(content)
                return SwarmResult(
                    role=role,
                    status="SUCCESS",
                    data=parsed,
                    raw_response=content,
                    duration_seconds=duration,
                    tokens_used=tokens,
                )
            except Exception as e:
                duration = asyncio.get_event_loop().time() - start_time
                return SwarmResult(
                    role=role,
                    status="ERROR",
                    data=None,
                    raw_response=str(e),
                    duration_seconds=duration,
                )


class AnthropicSwarmBackend(BaseSwarmBackend):
    """
    Executes tasks using the Anthropic Claude Messages API.
    Requires ANTHROPIC_API_KEY.
    """

    def __init__(
        self,
        default_model: str = "claude-3-5-haiku-20241022",
        api_key: Optional[str] = None,
        max_concurrency: int = 4,
    ):
        super().__init__(default_model=default_model, max_concurrency=max_concurrency)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    async def spawn(
        self,
        prompt: str,
        role: str = "Micro-Worker",
        model: Optional[str] = None,
        effort: Optional[str] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        input_data: Optional[Any] = None,
    ) -> SwarmResult:
        async with self.semaphore:
            target_model = model or self.default_model

            full_prompt = prompt
            if input_data is not None:
                formatted_input = json.dumps(input_data, indent=2, ensure_ascii=False) if isinstance(input_data, (dict, list)) else str(input_data)
                full_prompt += f"\n\n--- INPUT DATA ---\n{formatted_input}\n--- END INPUT DATA ---"

            system_instruction = (
                f"You are a specialized micro-worker agent with the role: '{role}'. "
                f"Solve the task objectively, concisely, and rigorously. Answer directly without preamble."
            )
            if json_schema:
                system_instruction += f"\nYou MUST respond strictly in valid JSON matching this schema: {json.dumps(json_schema)}"

            payload = {
                "model": target_model,
                "max_tokens": 4096,
                "system": system_instruction,
                "messages": [{"role": "user", "content": full_prompt}],
                "temperature": 0.2,
            }

            start_time = asyncio.get_event_loop().time()

            try:
                loop = asyncio.get_event_loop()
                data_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    "https://api.anthropic.com/v1/messages",
                    data=data_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "User-Agent": "Mimir-Swarm/2.0",
                    },
                    method="POST",
                )

                def _do_request():
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        return resp.read().decode("utf-8")

                resp_str = await loop.run_in_executor(None, _do_request)
                duration = asyncio.get_event_loop().time() - start_time

                resp_json = json.loads(resp_str)
                content_blocks = resp_json.get("content", [])
                content = "".join([b.get("text", "") for b in content_blocks if b.get("type") == "text"])
                tokens = resp_json.get("usage", {}).get("input_tokens", 0) + resp_json.get("usage", {}).get("output_tokens", 0)

                parsed = self.parse_json_from_text(content)
                return SwarmResult(
                    role=role,
                    status="SUCCESS",
                    data=parsed,
                    raw_response=content,
                    duration_seconds=duration,
                    tokens_used=tokens,
                )
            except Exception as e:
                duration = asyncio.get_event_loop().time() - start_time
                return SwarmResult(
                    role=role,
                    status="ERROR",
                    data=None,
                    raw_response=str(e),
                    duration_seconds=duration,
                )


def create_swarm_backend(
    backend_type: Optional[str] = None,
    model: Optional[str] = None,
    max_concurrency: int = 4,
    effort: Optional[str] = None,
    timeout_seconds: float = 180,
) -> BaseSwarmBackend:
    """
    Factory function for instantiating the optimal swarm backend.
    Auto-detects based on environment if backend_type is None or 'auto'.
    """
    chosen = (backend_type or "auto").lower()
    if chosen == "auto":
        chosen = os.environ.get("MIMIR_BACKEND", "auto").lower()
    chosen = {"antigravity": "agy", "openai-codex": "codex", "claude-code": "claude"}.get(chosen, chosen)
    selected_effort = effort or os.environ.get("MIMIR_EFFORT", "low")
    if timeout_seconds <= 0:
        raise ValueError("Worker timeout must be positive.")
    if chosen in ("agy", "codex", "claude") and selected_effort not in ("low", "medium", "high", "xhigh", "max"):
        raise ValueError("CLI effort must be low, medium, high, xhigh, or max. OpenCode accepts provider variants or none.")

    if chosen == "auto":
        # Preserve CLI discovery order. Skill invocation supplies --backend
        # explicitly; discovery never falls through into separately billed HTTP.
        for candidate in ("agy", "codex", "claude", "opencode"):
            try:
                return create_swarm_backend(candidate, model, max_concurrency, selected_effort, timeout_seconds)
            except FileNotFoundError:
                continue
        raise FileNotFoundError("No supported CLI found. Install/login to a CLI or explicitly select an HTTP backend.")

    selected_model = model or os.environ.get(f"MIMIR_{chosen.upper()}_MODEL") or os.environ.get("MIMIR_MODEL")

    if chosen in ("agy", "antigravity"):
        result = AgySwarmBackend(default_model=selected_model or "gemini-3.8-flash-low", default_effort=selected_effort, max_concurrency=max_concurrency)
    elif chosen in ("codex", "openai-codex"):
        result = CodexSwarmBackend(default_model=selected_model, default_effort=selected_effort, max_concurrency=max_concurrency)
    elif chosen == "claude":
        result = ClaudeCodeSwarmBackend(default_model=selected_model or "haiku", default_effort=selected_effort, max_concurrency=max_concurrency)
    elif chosen == "opencode":
        result = OpenCodeSwarmBackend(default_model=selected_model, default_effort=selected_effort, max_concurrency=max_concurrency)
    elif chosen in ("openai", "ollama", "vllm", "openrouter"):
        result = OpenAISwarmBackend(default_model=selected_model or "gpt-4o-mini", max_concurrency=max_concurrency)
    elif chosen == "anthropic":
        result = AnthropicSwarmBackend(default_model=selected_model or "claude-3-5-haiku-20241022", max_concurrency=max_concurrency)
    else:
        raise ValueError(f"Unknown Mímir backend: '{chosen}'. Supported: agy, codex, claude, opencode, openai, anthropic, ollama, auto.")
    result.default_effort = selected_effort
    result.timeout_seconds = timeout_seconds
    return result
