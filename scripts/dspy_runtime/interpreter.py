"""Deno interpreter policy and guarded upstream nested predictor facade."""
from __future__ import annotations

import threading
import functools

from dspy_runtime.engines import depth_context, parent_context


class InterpreterFactory:
    execution_instructions = "Python runs in Deno/Pyodide. Host files, environment, network and process execution are unavailable. Use only supplied corpus and approved tools. Nested dspy.Predict and dspy.RLM accept a signature ONLY, with no constructor kwargs. Runtime policy is injected automatically. Child RLMs must finish with SUBMIT and must not create deeper predictors."

    def __init__(self, channel, budget):
        self.channel = channel
        self.budget = budget
        self.active = 0
        self.sequence = 0
        self.lock = threading.Lock()

    def __deepcopy__(self, memo):
        # GEPA copies instructions; the injected runtime policy/channel stays owned.
        return self

    def __call__(self):
        import dspy
        from dspy.primitives.facade import CALL_TOOL, CONSTRUCT_TOOL
        factory = self
        depth = depth_context.get()
        with self.lock:
            if depth > self.budget["max_depth"] or self.active >= self.budget["max_interpreters"]:
                self.channel.call("trace", {"kind": "policy_failure", "reason": "interpreter_budget"})
                raise RuntimeError("Interpreter depth/resource budget exhausted")
            self.active += 1
            self.sequence += 1
            invocation = f"interpreter-{self.sequence}"
        factory.channel.call("interpreter", {"action": "open", "id": invocation, "depth": depth})

        class GuardedInterpreter(dspy.PythonInterpreter):
            def __init__(self):
                super().__init__(enable_read_paths=[], enable_write_paths=[], enable_env_vars=[],
                                 enable_network_access=[], sync_files=False)
                self.closed = False
                self.guarded = False
                self.kinds = {}

            def _guard_tools(self):
                if self.guarded or CONSTRUCT_TOOL not in self.tools:
                    return
                for name in ("llm_query", "llm_query_batched"):
                    if name not in self.tools:
                        continue
                    def wrap(func, tool_name):
                        @functools.wraps(func)
                        def bounded(*args, **kwargs):
                            try:
                                return func(*args, **kwargs)
                            except BaseException:
                                factory.channel.call("trace", {"kind": "policy_failure", "reason": tool_name + "_failed"})
                                raise
                        return bounded
                    self.tools[name] = wrap(self.tools[name], name)
                construct = self.tools[CONSTRUCT_TOOL]
                call = self.tools[CALL_TOOL]

                def guarded_construct(kind, signature, attr_name, kwargs=None):
                    # Nested RLM uses fixed policy. Reject other code/tool planners.
                    if factory.budget["max_depth"] == 0 or kind not in {"Predict", "RLM"}:
                        factory.channel.call("trace", {"kind": "policy_failure", "reason": "predictor_kind"})
                        raise RuntimeError("Nested predictor kind disabled")
                    if kwargs:
                        factory.channel.call("trace", {"kind": "policy_failure", "reason": "predictor_override"})
                        raise RuntimeError("Nested predictors cannot override runtime policy")
                    self.kinds[attr_name] = kind
                    if kind == "RLM":
                        kwargs = {"max_iters": factory.budget["max_iters"],
                                  "max_llm_calls": factory.budget["max_subcalls"],
                                  "max_output_chars": factory.budget["max_output_chars"]}
                    return construct(kind, signature, attr_name, kwargs)

                def guarded_call(handle, inputs=None):
                    if handle not in self.kinds or depth >= factory.budget["max_depth"]:
                        factory.channel.call("trace", {"kind": "policy_failure", "reason": "predictor_depth"})
                        raise RuntimeError("Nested predictor depth exhausted")
                    token = depth_context.set(depth + 1)
                    parent = parent_context.set(invocation)
                    try:
                        factory.channel.call("trace", {"kind": "child", "parent": invocation,
                                                       "depth": depth + 1, "predictor": self.kinds[handle]})
                        value = call(handle, inputs)
                        if self.kinds[handle] == "RLM" and (not value.get("trajectory") or not value["trajectory"][-1]["output"].startswith("FINAL:")):
                            factory.channel.call("trace", {"kind": "policy_failure", "reason": "child_iteration_budget"})
                            raise RuntimeError("Nested RLM iteration budget exhausted")
                        return value
                    finally:
                        parent_context.reset(parent)
                        depth_context.reset(token)

                self.tools[CONSTRUCT_TOOL] = guarded_construct
                self.tools[CALL_TOOL] = guarded_call
                self.guarded = True

            def execute(self, code, variables=None):
                self._guard_tools()
                token = depth_context.set(depth)
                parent = parent_context.set(invocation)
                try:
                    factory.channel.call("trace", {"kind": "code", "invocation": invocation,
                                                   "depth": depth, "code": code})
                    return super().execute(code, variables=variables)
                finally:
                    parent_context.reset(parent)
                    depth_context.reset(token)

            def shutdown(self):
                try:
                    super().shutdown()
                finally:
                    if not self.closed:
                        with factory.lock:
                            factory.active -= 1
                        self.closed = True
                        factory.channel.call("interpreter", {"action": "close", "id": invocation, "depth": depth})
        return GuardedInterpreter()
