"""Provider credential scope and learning-state isolation regression tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import diagnostics
from jarvis_memory import JarvisMemory
from mimir_config import ConfigurationRequired


class NativePreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "codex"
        self.home.mkdir()
        (self.home / "config.toml").write_text(
            'model_provider="azure"\n[model_providers.azure]\nenv_key="TEST_NATIVE_KEY"\n', encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_key_is_actionable_before_worker_start(self):
        with patch.dict(os.environ, {"CODEX_HOME": str(self.home)}, clear=True), \
             patch.object(diagnostics, "_persistent_environment", return_value=None):
            status, overrides = diagnostics.native_environment("codex", workspace=self.root)
            self.assertFalse(status["ready"])
            self.assertEqual(overrides, {})
            with self.assertRaisesRegex(ConfigurationRequired, "TEST_NATIVE_KEY"):
                diagnostics.require_ready(status)

    def test_user_key_returns_private_override_without_environment_mutation(self):
        with patch.dict(os.environ, {"CODEX_HOME": str(self.home)}, clear=True), \
             patch.object(diagnostics, "_persistent_environment", side_effect=lambda n, s: "private-value" if s == "User" else None):
            status, overrides = diagnostics.native_environment("codex", workspace=self.root)
            self.assertTrue(status["ready"])
            self.assertEqual(overrides, {"TEST_NATIVE_KEY": "private-value"})
            self.assertNotIn("TEST_NATIVE_KEY", os.environ)
            self.assertNotIn("private-value", json.dumps(status))
            self.assertEqual(status["required_environment"][0]["source"], "User")

    def test_empty_process_variable_suppresses_persisted_hydration(self):
        with patch.dict(os.environ, {"CODEX_HOME": str(self.home), "TEST_NATIVE_KEY": ""}, clear=True), \
             patch.object(diagnostics, "_persistent_environment", return_value="persisted"):
            status, overrides = diagnostics.native_environment("codex", workspace=self.root)
            self.assertEqual(overrides, {})
            self.assertFalse(status["ready"])

    def test_process_key_takes_precedence_over_user_and_machine(self):
        with patch.dict(os.environ, {"CODEX_HOME": str(self.home), "TEST_NATIVE_KEY": "process-secret"}, clear=True), \
             patch.object(diagnostics, "_persistent_environment", return_value="persistent-secret"):
            status, overrides = diagnostics.native_environment("codex", workspace=self.root)
            self.assertTrue(status["ready"])
            self.assertFalse(overrides)
            self.assertEqual(status["required_environment"][0]["source"], "Process")
            self.assertNotIn("secret", json.dumps(status))

    def test_other_harness_never_hydrates_user_secret(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(diagnostics, "_persistent_environment", return_value="user-secret"):
            status, overrides = diagnostics.native_environment("anthropic", workspace=self.root)
            self.assertFalse(status["ready"])
            self.assertEqual(overrides, {})

    def test_trusted_ancestor_provider_override_retains_environment_key(self):
        config = (self.home / "config.toml").read_text()
        config += "\n[projects." + json.dumps(str(self.root)) + "]\ntrust_level=\"trusted\"\n"
        (self.home / "config.toml").write_text(config)
        (self.root / ".codex").mkdir()
        (self.root / ".codex" / "config.toml").write_text(
            '[model_providers.azure]\nname="project override"\n', encoding="utf-8")
        child = self.root / "subfolder"
        child.mkdir()
        with patch.dict(os.environ, {"CODEX_HOME": str(self.home), "TEST_NATIVE_KEY": "value"}, clear=True), \
             patch.object(diagnostics, "_persistent_environment", return_value=None):
            status, _ = diagnostics.native_environment("codex", workspace=child)
        self.assertTrue(status["ready"])
        self.assertEqual(status["required_environment"][0]["name"], "TEST_NATIVE_KEY")
        self.assertIn(str(self.root / ".codex" / "config.toml"), status["config_paths"])

    def test_untrusted_project_provider_override_is_not_loaded(self):
        (self.root / ".codex").mkdir()
        (self.root / ".codex" / "config.toml").write_text(
            'model_provider="malicious"\n', encoding="utf-8")
        with patch.dict(os.environ, {"CODEX_HOME": str(self.home), "TEST_NATIVE_KEY": "value"}, clear=True):
            status, _ = diagnostics.native_environment("codex", workspace=self.root)
        self.assertEqual(status["provider"], "azure")

    def test_invalid_toml_diagnostics_do_not_copy_content(self):
        (self.home / "config.toml").write_text('model_provider = "private-key\n', encoding="utf-8")
        with patch.dict(os.environ, {"CODEX_HOME": str(self.home)}, clear=True):
            status, _ = diagnostics.native_environment("codex", workspace=self.root)
            self.assertFalse(status["ready"])
            self.assertNotIn("private-key", json.dumps(status))

    def test_collect_reports_identity_scoped_memory_and_no_inference(self):
        with patch.dict(os.environ, {"CODEX_HOME": str(self.home), "TEST_NATIVE_KEY": "secret"}, clear=True):
            report = diagnostics.collect_diagnostics("codex", "gpt-6.1-sol", "low", workspace=self.root)
        self.assertEqual(report["memory"]["mode"], "read")
        self.assertEqual(report["memory"]["guidance_path"], str(self.root / ".mimir" / "LEARNINGS.md"))
        self.assertEqual(len(report["runtime"]["content_sha256"]), 64)
        self.assertNotIn("secret", json.dumps(report))
        self.assertFalse((self.root / ".mimir").exists())


class ExplicitMemoryTests(unittest.TestCase):
    def test_read_and_off_modes_create_no_state_and_never_append(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for mode in ("read", "off"):
                memory = JarvisMemory(mode=mode, workspace=root)
                self.assertEqual(memory.load_memory_context("topic"), "")
                self.assertFalse(memory.record_learning("goal", "takeaway", "reflection"))
                self.assertFalse((root / ".mimir").exists())

    def test_write_creates_candidates_separate_from_guidance_and_idempotent(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            memory = JarvisMemory(mode="write", workspace=root)
            for _ in range(2):
                self.assertTrue(memory.record_learning("goal", "not validated", "reflection", report_path="report.md"))
            records = [json.loads(line) for line in memory.candidate_path.read_text().splitlines()]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["status"], "requires_independent_validation")
            self.assertFalse(memory.guidance_path.exists())
            self.assertEqual(memory.load_memory_context("goal"), "")

    def test_workspace_legacy_guidance_readonly_and_candidates_not_reinjected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "LEARNINGS.md"
            legacy.write_text("# Curated\nUse source provenance.\n", encoding="utf-8")
            before = legacy.read_bytes()
            memory = JarvisMemory(mode="write", workspace=root)
            self.assertTrue(memory.record_learning("goal", "unvalidated candidate", ""))
            context = memory.load_memory_context()
            self.assertIn("source provenance", context)
            self.assertNotIn("unvalidated candidate", context)
            self.assertEqual(legacy.read_bytes(), before)

    def test_configured_guidance_precedes_legacy(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "LEARNINGS.md").write_text("old", encoding="utf-8")
            path = root / "shared" / "curated.md"
            path.parent.mkdir()
            path.write_text("approved guidance", encoding="utf-8")
            memory = JarvisMemory(str(path), mode="read", workspace=root)
            self.assertEqual(memory.load_memory_context(), "approved guidance")
            self.assertEqual(memory.candidate_path, path.parent / "learning-candidates.jsonl")

    def test_legacy_fallback_excludes_historical_generated_candidates(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "LEARNINGS.md"
            path.write_text("# Standing guidance\nCheck primary sources.\n\n"
                            "### [2026-10-22 12:00 UTC] Objective: goal\n"
                            "- Old generated takeaway should not be promoted.\n", encoding="utf-8")
            before = path.read_bytes()
            memory = JarvisMemory(mode="read", workspace=root)
            context = memory.load_memory_context("goal")
            self.assertIn("unvalidated", context)
            self.assertIn("Check primary sources", context)
            self.assertNotIn("Old generated takeaway", context)
            self.assertEqual(path.read_bytes(), before)
            resumed = JarvisMemory(str(memory.memory_path), mode="read", workspace=root)
            self.assertNotIn("Old generated takeaway", resumed.load_memory_context("goal"))
            explicit = JarvisMemory(str(path), mode="read", workspace=root)
            self.assertIn("Old generated takeaway", explicit.load_memory_context("goal"))

    def test_torn_candidate_append_is_explicit_and_preserved(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            memory = JarvisMemory(mode="write", workspace=root)
            memory.candidate_path.parent.mkdir(parents=True)
            memory.candidate_path.write_text('{"candidate_id":', encoding="utf-8")
            before = memory.candidate_path.read_bytes()
            self.assertFalse(memory.record_learning("goal", "solution", ""))
            self.assertIn("incomplete record", memory.last_error)
            self.assertEqual(memory.candidate_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
