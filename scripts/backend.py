"""
scripts/backend.py
Universal Multi-Backend Swarm Engine for M Í M I R.
Abstracts LLM execution across:
- Antigravity CLI (agy.exe) - Zero API keys, local authenticated session
- OpenAI API & Compatible endpoints (Ollama, LMStudio, vLLM, OpenRouter)
- Anthropic Claude API (Claude 3.5 Haiku, Claude 3.7 Sonnet)
- Generic CLI wrappers
"""

from __future__ import annotations

import asyncio
import atexit
import json
import os
import re
import shutil
import tempfile
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
    effort: str = "low"  # low | medium | high
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
        self.default_model = default_model
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
                        effort="low",
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


class AgySwarmBackend(BaseSwarmBackend):
    """
    Spawns headless agy.exe processes using the user's existing
    authenticated AGY CLI session. Zero API keys or extra billing required.
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
        self.isolate_sessions = isolate_sessions
        self._temp_home: Optional[str] = None
        self._isolated_env: Optional[Dict[str, str]] = None

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

    def _ensure_isolated_env(self) -> Dict[str, str]:
        if self._isolated_env is not None:
            return self._isolated_env

        temp_dir = tempfile.mkdtemp(prefix="agy_swarm_isolated_")
        self._temp_home = temp_dir

        temp_gemini = Path(temp_dir) / ".gemini"
        temp_gemini.mkdir(parents=True, exist_ok=True)
        real_gemini = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".gemini"

        for auth_file in ["oauth_creds.json", "google_accounts.json", "installation_id"]:
            src = real_gemini / auth_file
            if src.exists():
                try:
                    shutil.copy2(src, temp_gemini / auth_file)
                except Exception:
                    pass

        env = os.environ.copy()
        env["USERPROFILE"] = temp_dir
        env["HOME"] = temp_dir
        self._isolated_env = env

        def _cleanup_handler():
            if self._temp_home and os.path.exists(self._temp_home):
                try:
                    shutil.rmtree(self._temp_home, ignore_errors=True)
                except Exception:
                    pass

        atexit.register(_cleanup_handler)
        return self._isolated_env

    def cleanup(self) -> None:
        if self._temp_home and os.path.exists(self._temp_home):
            try:
                shutil.rmtree(self._temp_home, ignore_errors=True)
            except Exception:
                pass
            self._temp_home = None
            self._isolated_env = None

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
                f"Du är en högspecialiserad mikro-agent med rollen: '{role}'. "
                f"Lös uppgiften koncist, sakligt och strukturerat. Svara direkt utan onödig hälsningsfras."
            )

            cmd = [
                self.agy_path,
                "--model",
                target_model,
                "--effort",
                target_effort,
                "--output-format",
                "json",
            ]

            if json_schema:
                cmd.extend(["--json-schema", json.dumps(json_schema)])

            cmd.extend(["-p", f"{system_instruction}\n\n{full_prompt}"])

            start_time = asyncio.get_event_loop().time()
            sub_env = self._ensure_isolated_env() if self.isolate_sessions else None
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=sub_env,
            )

            stdout, stderr = await proc.communicate()
            duration = asyncio.get_event_loop().time() - start_time

            raw_out = stdout.decode("utf-8", errors="replace").strip()
            raw_err = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                return SwarmResult(
                    role=role,
                    status="ERROR",
                    data=None,
                    raw_response=raw_err or raw_out,
                    duration_seconds=duration,
                )

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
) -> BaseSwarmBackend:
    """
    Factory function for instantiating the optimal swarm backend.
    Auto-detects based on environment if backend_type is None or 'auto'.
    """
    chosen = (backend_type or os.environ.get("MIMIR_BACKEND", "auto")).lower()

    if chosen == "auto":
        # 1. Prefer agy if binary is present
        if shutil.which("agy") or Path(os.environ.get("LOCALAPPDATA", "")) / "agy" / "bin" / "agy.exe":
            try:
                return AgySwarmBackend(default_model=model or "gemini-3.8-flash-low", max_concurrency=max_concurrency)
            except Exception:
                pass

        # 2. Check OpenAI API Key
        if os.environ.get("OPENAI_API_KEY"):
            return OpenAISwarmBackend(default_model=model or "gpt-4o-mini", max_concurrency=max_concurrency)

        # 3. Check Anthropic API Key
        if os.environ.get("ANTHROPIC_API_KEY"):
            return AnthropicSwarmBackend(default_model=model or "claude-3-5-haiku-20241022", max_concurrency=max_concurrency)

        # Fallback to agy attempt
        chosen = "agy"

    if chosen in ("agy", "antigravity"):
        return AgySwarmBackend(default_model=model or "gemini-3.8-flash-low", max_concurrency=max_concurrency)
    elif chosen in ("openai", "ollama", "vllm", "openrouter"):
        return OpenAISwarmBackend(default_model=model or "gpt-4o-mini", max_concurrency=max_concurrency)
    elif chosen in ("anthropic", "claude"):
        return AnthropicSwarmBackend(default_model=model or "claude-3-5-haiku-20241022", max_concurrency=max_concurrency)
    else:
        raise ValueError(f"Unknown Mímir backend: '{chosen}'. Supported: 'agy', 'openai', 'anthropic', 'auto'.")
