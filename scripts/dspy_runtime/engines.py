"""Normalized DSPy engines calling the parent-owned native broker."""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import fields

depth_context = ContextVar("mimir_rlm_depth", default=0)
parent_context = ContextVar("mimir_rlm_parent", default="root")


class NativeEngine:
    def __init__(self, channel, model=None):
        self.channel = channel
        self.model = model

    def complete(self, request):
        from dspy.lm15 import Message, Response, Usage
        from dspy.lm15 import InvalidRequestError
        if self.model and request.model != "mimir/" + self.model:
            raise InvalidRequestError("Native model profile cannot be overridden")
        # Fixed native profile: generation/tool overrides cannot escape policy.
        if request.tools:
            raise InvalidRequestError("Native DSPy bridge accepts text only, without native tools")
        for field in fields(request.config):
            value = getattr(request.config, field.name)
            if value not in (None, (), [], {}):
                raise InvalidRequestError(f"Unsupported native generation control: {field.name}")
        messages = []
        for message in request.messages:
            role = getattr(message.role, "value", message.role)
            if role not in {"user", "assistant", "system", "developer"}:
                raise InvalidRequestError("Unsupported native message role")
            parts = getattr(message, "parts", ())
            text = []
            for part in parts:
                if type(part).__name__ != "TextPart":
                    raise InvalidRequestError("Native DSPy bridge accepts text parts only")
                text.append(part.text)
            messages.append({"role": role, "text": "\n".join(text)})
        if request.system is not None and not isinstance(request.system, str):
            raise InvalidRequestError("Native DSPy bridge accepts textual system instructions only")
        payload = {"messages": messages, "instructions": request.system,
                   "depth": depth_context.get(), "parent": parent_context.get()}
        result = self.channel.call("lm", payload)
        return Response(id=result["operation_id"], model=request.model,
                        message=Message.assistant(result["text"]), finish_reason="stop",
                        usage=Usage(), provider_data={"mimir": {
                            "native_reported_total_tokens": result.get("tokens"),
                            "usage_scope": "native agent turn; token breakdown unavailable"}})


class AsyncNativeEngine:
    def __init__(self, engine):
        self.engine = engine

    async def complete(self, request):
        return await asyncio.to_thread(self.engine.complete, request)
