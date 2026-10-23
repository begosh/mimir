"""Actual pinned MCP stdio client/server protocol, not decorator mocks."""
import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.session import ClientSession

class StdioProtocol(unittest.IsolatedAsyncioTestCase):
    async def test_handshake_tools_annotations_and_sanitized_unknown_run(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            parameters = StdioServerParameters(command=sys.executable,
                         args=["-u", str(repo / "scripts/mcp_server.py"), "--run-root", directory])
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as client:
                    hello = await asyncio.wait_for(client.initialize(), 15)
                    self.assertEqual(hello.server_info.name, "mimir")
                    listed = await client.list_tools()
                    tools = {t.name: t for t in listed.tools}
                    self.assertEqual(set(tools), {"start_run", "get_status", "cancel_run", "get_result", "get_diagnostics"})
                    self.assertTrue(tools["get_diagnostics"].annotations.read_only_hint)
                    self.assertTrue(tools["get_diagnostics"].annotations.open_world_hint)
                    self.assertIn("check_search", tools["get_diagnostics"].input_schema["properties"])
                    diagnostic = await client.call_tool("get_diagnostics", {"backend": "codex"})
                    self.assertFalse(diagnostic.is_error)
                    self.assertTrue(tools["get_status"].annotations.read_only_hint)
                    self.assertFalse(tools["start_run"].annotations.destructive_hint)
                    for name in ("research_program", "research_budget", "source_manifest", "program_manifest", "task_brief", "recursive_plan", "planning_budget", "max_depth"):
                        self.assertIn(name, tools["start_run"].input_schema["properties"])
                    result = await client.call_tool("get_status", {"run_id": "../secret"})
                    self.assertTrue(result.is_error)
                    self.assertNotIn("SECRET-KEY", str(result))

    async def test_real_stdio_narration_and_optional_diagnostic_events(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            run_id = "b" * 32
            root = Path(directory) / run_id
            root.mkdir()
            events = [{"sequence": 1, "event": "task_submitted", "node_id": "critique",
                       "output_excerpt": "RAW-PRIVATE-OUTPUT"},
                      {"sequence": 2, "event": "execute_completed", "elapsed_seconds": 4}]
            (root / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
            (root / "run.json").write_text(json.dumps({"run_id": run_id, "status": "completed",
                "phase": "execute", "completed_phase": "execute", "sequence": 2,
                "latest_event": events[-1]}), encoding="utf-8")
            params = StdioServerParameters(command=sys.executable,
                args=["-u", str(repo / "scripts/mcp_server.py"), "--run-root", directory])
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    await asyncio.wait_for(client.initialize(), 15)
                    result = await client.call_tool("get_status", {"run_id": run_id, "wait_seconds": 0})
                    self.assertFalse(result.is_error)
                    view = json.loads(result.content[0].text)
                    self.assertTrue(view["narration"])
                    self.assertTrue(view["updates"])
                    self.assertNotIn("RAW-PRIVATE-OUTPUT", str(result))
                    self.assertNotIn("events", view)
                    detail = await client.call_tool("get_status", {"run_id": run_id,
                        "wait_seconds": 0, "include_events": True})
                    self.assertFalse(detail.is_error)
                    self.assertEqual(json.loads(detail.content[0].text)["events"], events)
