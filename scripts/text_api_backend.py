"""Explicit Responses transport for text-only work; no agent session or tools."""
import asyncio
import hashlib
import json
import os
import ssl
import time
from urllib.parse import urlsplit

from backend import BaseSwarmBackend, SwarmResult, has_worker_result
from mimir_config import ConfigurationRequired


def configured_value(name):
    value = os.environ.get(name)
    if value:
        return value
    from diagnostics import _persistent_environment
    return _persistent_environment(name, "User") or _persistent_environment(name, "Machine")


class TextResponsesBackend(BaseSwarmBackend):
    """Stateless requests with strict schema, explicit effort and measured usage."""
    def __init__(self, model, *, provider=None, endpoint=None, api_key=None,
                 effort="low", max_concurrency=4, client=None):
        super().__init__(model, max_concurrency)
        self.default_effort = effort
        self.provider = provider or configured_value("MIMIR_TEXT_API_PROVIDER") or (
            "azure" if configured_value("AZURE_OPENAI_ENDPOINT") else "openai")
        if self.provider not in {"azure", "openai"}:
            raise ConfigurationRequired("Text API provider must be azure or openai")
        root = endpoint or configured_value("AZURE_OPENAI_ENDPOINT" if self.provider == "azure" else "OPENAI_BASE_URL")
        root = (root or "https://api.openai.com/v1").rstrip("/")
        if self.provider == "azure":
            if not endpoint and not configured_value("AZURE_OPENAI_ENDPOINT"):
                raise ConfigurationRequired("Missing environment variable AZURE_OPENAI_ENDPOINT")
            if root.endswith("/openai/v1"):
                pass
            elif not urlsplit(root).path.strip("/"):
                root += "/openai/v1"
            else:
                raise ConfigurationRequired("Azure text endpoint must be a resource root or /openai/v1")
        parts = urlsplit(root)
        if parts.scheme != "https" or parts.username or parts.password or parts.query or parts.fragment:
            raise ConfigurationRequired("Text API endpoint requires HTTPS without embedded credentials or query")
        self.endpoint = root
        self._key = api_key or configured_value("AZURE_OPENAI_API_KEY" if self.provider == "azure" else "OPENAI_API_KEY")
        if not self._key:
            raise ConfigurationRequired("Missing environment variable " + (
                "AZURE_OPENAI_API_KEY" if self.provider == "azure" else "OPENAI_API_KEY"))
        if effort not in {"low", "medium", "high", "xhigh", "max"}:
            raise ConfigurationRequired("Choose an explicit supported reasoning effort")
        self._client = client
        self._owned_client = client is None
        self.transport = "responses"
        self.execution_identity = {"transport": "responses", "provider": self.provider,
            "endpoint_hash": hashlib.sha256(root.encode()).hexdigest(), "model": model, "effort": effort}

    def _http_client(self):
        if self._client is None:
            import httpx
            context = ssl.create_default_context()
            extra = configured_value("SSL_CERT_FILE") or configured_value("NODE_EXTRA_CA_CERTS")
            if extra:
                context.load_verify_locations(extra)
            # No SDK/provider retries: every paid attempt belongs in the broker ledger.
            self._client = httpx.AsyncClient(verify=context, timeout=self.timeout_seconds)
        return self._client

    async def spawn_restricted(self, prompt, *, completion_instructions=None, **options):
        return await self.spawn(prompt, completion_instructions=completion_instructions, **options)

    async def spawn(self, prompt, role="Micro-Worker", model=None, effort=None,
                    json_schema=None, input_data=None, completion_instructions=None):
        async with self.semaphore:
            started = time.monotonic()
            full_prompt = prompt
            if input_data is not None:
                full_prompt += "\nINPUT DATA:\n" + json.dumps(input_data, ensure_ascii=False)
            payload = {"model": model or self.default_model, "reasoning": {"effort": effort or self.default_effort},
                       "input": [{"role": "user", "content": full_prompt}], "store": False, "tools": []}
            if completion_instructions:
                payload["instructions"] = completion_instructions
            if json_schema is not None:
                payload["text"] = {"format": {"type": "json_schema", "name": "mimir_output",
                    "strict": True, "schema": json_schema}}
            usage = None
            tokens = 0
            raw = ""
            parsed = None
            try:
                headers = {"api-key": self._key} if self.provider == "azure" else {"Authorization": "Bearer " + self._key}
                async with asyncio.timeout(self.timeout_seconds):
                    response = await self._http_client().post(self.endpoint + "/responses", json=payload, headers=headers)
                if response.status_code >= 400:
                    return SwarmResult(role, "ERROR", None,
                        f"Text API HTTP {response.status_code}; check model, endpoint, authentication and limits.",
                        time.monotonic() - started)
                body = response.json()
                billed = body.get("usage") or {}
                usage = {"input_tokens": billed.get("input_tokens", 0),
                    "cached_input_tokens": (billed.get("input_tokens_details") or {}).get("cached_tokens", 0),
                    "output_tokens": billed.get("output_tokens", 0),
                    "reasoning_output_tokens": (billed.get("output_tokens_details") or {}).get("reasoning_tokens", 0)}
                tokens = billed.get("total_tokens", usage["input_tokens"] + usage["output_tokens"])
                if body.get("model") and body["model"] != payload["model"]:
                    raise ValueError("Provider returned a different model")
                if body.get("status") != "completed":
                    raise ValueError("Provider result incomplete")
                messages = body.get("output", [])
                if any(item.get("type") not in {"message", "reasoning"} for item in messages):
                    raise ValueError("Unexpected output operation")
                blocks = [block for item in messages if item.get("type") == "message" for block in item.get("content", [])]
                if any(block.get("type") != "output_text" for block in blocks):
                    raise ValueError("Refused or unexpected content")
                raw = "".join(block.get("text", "") for block in blocks)
                parsed = json.loads(raw)
                if not has_worker_result(parsed):
                    raise ValueError("Empty result")
                if json_schema is not None:
                    from jsonschema import validate
                    validate(parsed, json_schema)
                return SwarmResult(role, "SUCCESS", parsed, raw, time.monotonic() - started,
                                   tokens_used=tokens, usage_details=usage)
            except asyncio.CancelledError:
                raise
            except Exception:
                return SwarmResult(role, "ERROR", None,
                    "Text API returned no usable schema-valid result; check connection, model and output status.",
                    time.monotonic() - started, tokens_used=tokens, usage_details=usage,
                    rejected_output={"raw_response": raw, "data": parsed} if raw else None)

    async def aclose(self):
        if self._owned_client and self._client is not None:
            await self._client.aclose()

    async def check_cli(self):
        return {"transport": "responses", "provider": self.provider, "model": self.default_model,
                "effort": self.default_effort, "configuration_ready": True,
                "verification": "Configuration only; authentication and model access not tested"}


class HybridSwarmBackend(BaseSwarmBackend):
    """Native tools on spawn; direct text requests on spawn_restricted."""
    def __init__(self, native, text, *, tool_factory=None, tool_backend_name="codex", tool_model=None):
        super().__init__(text.default_model, text.max_concurrency)
        if native is not None and (native.default_model, native.default_effort) != (text.default_model, text.default_effort):
            raise ConfigurationRequired("Hybrid routes must keep the same model and effort")
        self.tool_backend, self.text_backend = native, text
        self._tool_factory = tool_factory
        self._tool_lock = asyncio.Lock()
        self.tool_backend_name = tool_backend_name
        self.tool_model = tool_model or text.default_model
        self.default_effort = text.default_effort
        self.transport = "hybrid"
        self.research_tool_policy = f"Direct Responses for text-only operations; {tool_backend_name} tools initialized only when needed"
        native_identity = getattr(native, "execution_identity", None)
        if tool_backend_name == "codex" and (native is None or getattr(native, "_native_config", False)):
            from diagnostics import native_environment
            from pathlib import Path
            info, _ = native_environment("codex")
            native_identity = {"provider": info.get("provider"), "config_hashes": [
                hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in info.get("config_paths", [])]}
        self.execution_identity = {"transport": "hybrid", "tool_backend": tool_backend_name,
                                   "tool_model": self.tool_model, "tools": native_identity, "text": text.execution_identity}

    async def _tools(self):
        async with self._tool_lock:
            if self.tool_backend is None:
                if self._tool_factory is None:
                    raise ConfigurationRequired("This run has no configured tool runtime")
                candidate = self._tool_factory()
                candidate.timeout_seconds = self.timeout_seconds
                try:
                    if hasattr(candidate, "check_cli"):
                        await candidate.check_cli()
                except BaseException:
                    await candidate.aclose()
                    raise
                self.tool_backend = candidate
        return self.tool_backend

    async def spawn(self, *args, **options):
        tools = await self._tools()
        tools.timeout_seconds = self.timeout_seconds
        if options.get("model") not in (None, self.default_model):
            raise ConfigurationRequired("Tool dispatch cannot change the selected model")
        options["model"] = self.tool_model
        return await tools.spawn(*args, **options)

    async def spawn_restricted(self, *args, **options):
        self.text_backend.timeout_seconds = self.timeout_seconds
        return await self.text_backend.spawn_restricted(*args, **options)

    async def check_cli(self):
        return {"transport": "hybrid", "model": self.default_model, "effort": self.default_effort,
                "text_provider": self.text_backend.provider, "text_configuration_ready": True,
                "tool_backend": self.tool_backend_name, "tool_model": self.tool_model, "tools": "Deferred until tool-using work",
                "verification": "Configuration only; authentication and model access not tested"}

    async def aclose(self):
        try:
            await self.text_backend.aclose()
        finally:
            if self.tool_backend is not None:
                await self.tool_backend.aclose()
