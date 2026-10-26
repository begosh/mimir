"""First-use consent, saved preferences and override behavior; no provider calls."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import engine as mimir
from mimir_config import (ConfigurationRequired, config_path, config_status,
                          configure, load_config, resolve_execution, validate)


class ProjectConfiguration(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / ".mimir/config.json"
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_discovery_suggests_known_host_model_without_saving(self):
        with patch("shutil.which", return_value="installed"):
            status = config_status("codex", self.path, host_model="gpt-6.1-sol")
        self.assertEqual(status["suggested_backend"], "codex")
        self.assertEqual(status["suggested_model"], "gpt-6.1-sol")
        self.assertEqual(status["suggested_effort"], "low")
        self.assertTrue(status["confirmation_required"])
        self.assertFalse(self.path.exists())
        with self.assertRaises(ConfigurationRequired):
            resolve_execution(None, None, None, self.path)

    def test_unknown_host_does_not_guess_among_multiple_clis(self):
        with patch("shutil.which", return_value="installed"):
            status = config_status(path=self.path)
        self.assertIsNone(status["suggested_backend"])
        self.assertIsNone(status["suggested_model"])
        with patch("shutil.which", side_effect=lambda name: "installed" if name == "agy" else None):
            status = config_status("codex", self.path, host_model="wrong-host-model")
        self.assertEqual(status["suggested_backend"], "agy")
        self.assertEqual(status["suggested_model"], "gemini-3.8-flash-low")

    def test_project_config_shared_from_nested_directory_and_worktree(self):
        (self.root / ".git").write_text("gitdir: external-worktree")
        nested = self.root / "src/submodule"
        nested.mkdir(parents=True)
        self.assertEqual(config_path(nested), self.path)
        configure("codex", "gpt-6.1-sol", "low", config_path(nested))
        self.assertEqual(load_config(config_path(self.root))["model"], "gpt-6.1-sol")
        elsewhere = self.root / "other"
        elsewhere.mkdir()
        (elsewhere / ".git").mkdir()
        self.assertEqual(config_path(elsewhere), elsewhere / ".mimir/config.json")

    def test_save_replace_and_schema_never_persist_credentials(self):
        first = configure("agy", path=self.path)
        self.assertEqual(load_config(self.path), first)
        second = configure("codex", "gpt-6.1-sol", "low", self.path)
        self.assertEqual(load_config(self.path), second)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
        self.assertEqual(set(second), {"version", "backend", "model", "effort"})
        invalid = [dict(second, api_key="must-not-save"), dict(second, version=True),
                   dict(second, backend=[]), dict(second, model=None), dict(second, effort="unknown"),
                   dict(second, backend="opencode", model="provider/")]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ConfigurationRequired):
                validate(value)
        with patch("mimir_config.os.replace", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                configure("claude", path=self.path)
        self.assertEqual(load_config(self.path), second)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_saved_choice_reused_across_hosts_without_implicit_model_upgrade(self):
        configure("codex", "gpt-6.1-sol", "low", self.path)
        with patch("shutil.which", return_value="installed"):
            status = config_status("opencode", self.path, host_model="provider/expensive")
        self.assertFalse(status["confirmation_required"])
        self.assertEqual(status["settings"]["backend"], "codex")
        self.assertEqual(resolve_execution(None, None, None, self.path), ("codex", "gpt-6.1-sol", "low"))
        self.assertEqual(resolve_execution("auto", None, None, self.path), ("codex", "gpt-6.1-sol", "low"))

    def test_arguments_environment_and_matching_profile_precedence(self):
        configure("codex", "saved", "low", self.path)
        with patch.dict(os.environ, {"MIMIR_MODEL": "generic", "MIMIR_CODEX_MODEL": "specific", "MIMIR_EFFORT": "medium"}):
            self.assertEqual(resolve_execution(None, None, None, self.path), ("codex", "specific", "medium"))
            self.assertEqual(resolve_execution("codex", "explicit", "high", self.path), ("codex", "explicit", "high"))
        before = self.path.read_bytes()
        self.assertEqual(resolve_execution("claude", None, None, self.path), ("claude", None, None))
        with patch.dict(os.environ, {"MIMIR_BACKEND": "claude"}):
            self.assertEqual(resolve_execution(None, None, None, self.path), ("claude", None, None))
            self.assertEqual(resolve_execution("codex", None, None, self.path), ("codex", "saved", "low"))
        self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_profile_requires_repair_but_explicit_override_can_run_once(self):
        self.path.parent.mkdir()
        self.path.write_text("not json", encoding="utf-8")
        with self.assertRaises(ConfigurationRequired):
            resolve_execution(None, None, None, self.path)
        self.assertEqual(resolve_execution("claude", None, None, self.path), ("claude", None, None))
        configure("opencode", "provider/model", "none", self.path)
        self.assertEqual(load_config(self.path)["effort"], "none")
        self.path.write_text(json.dumps(load_config(self.path)), encoding="utf-8-sig")
        self.assertEqual(load_config(self.path)["model"], "provider/model")

    def test_setup_commands_work_without_calls_or_learning(self):
        command = [sys.executable, "-B", str(Path(mimir.__file__).with_name("mimir.py"))]
        process_env = {**os.environ, "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows")}
        result = subprocess.run(command + ["--config-status", "--host", "codex", "--host-model", "gpt-6.1-sol"],
                                cwd=self.root, env=process_env, capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["configured"])
        self.assertFalse(self.path.exists())
        result = subprocess.run(command + ["--configure", "--backend", "codex", "--model", "gpt-6.1-sol", "--effort", "low"],
                                cwd=self.root, env=process_env, capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["settings"]["model"], "gpt-6.1-sol")
        self.assertFalse((self.root / "LEARNINGS.md").exists())

    def test_mimir_status_and_config_cli_commands(self):
        command = [sys.executable, "-B", str(Path(mimir.__file__).with_name("mimir.py"))]
        process_env = {**os.environ, "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows")}

        # 1. mimir status in unconfigured directory
        result = subprocess.run(command + ["status"],
                                cwd=self.root, env=process_env, capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("M Í M I R // System Status", result.stdout)

        # 2. mimir status --json
        result = subprocess.run(command + ["status", "--json"],
                                cwd=self.root, env=process_env, capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        diag = json.loads(result.stdout)
        self.assertIn("backend", diag)
        self.assertIn("ready", diag)

        # 3. mimir config view (unconfigured)
        result = subprocess.run(command + ["config"],
                                cwd=self.root, env=process_env, capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Not Configured", result.stdout)

        # 4. mimir config set with arguments
        result = subprocess.run(command + ["config", "--backend", "codex", "--model", "gpt-6.1-sol", "--effort", "low"],
                                cwd=self.root, env=process_env, capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Configuration updated in .mimir/config.json", result.stdout)
        self.assertTrue(self.path.exists())

        # 5. mimir config partial update (only model)
        result = subprocess.run(command + ["config", "model=custom-model"],
                                cwd=self.root, env=process_env, capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        saved = load_config(self.path)
        self.assertEqual(saved["model"], "custom-model")
        self.assertEqual(saved["backend"], "codex")
        self.assertEqual(saved["effort"], "low")

        # 6. mimir config --json view
        result = subprocess.run(command + ["config", "--json"],
                                cwd=self.root, env=process_env, capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        status_json = json.loads(result.stdout)
        self.assertTrue(status_json["configured"])
        self.assertEqual(status_json["settings"]["model"], "custom-model")


class ConfigurationBeforeExecution(unittest.IsolatedAsyncioTestCase):
    async def test_unconfigured_run_reports_setup_before_backend_or_memory(self):
        for profile in (None, "corrupt"):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / ".mimir/config.json"
                if profile:
                    path.parent.mkdir()
                    path.write_text(profile)
                progress = io.StringIO()
                with patch.dict(os.environ, {}, clear=True), patch("mimir_config.config_path", return_value=path), \
                     patch.object(mimir, "create_swarm_backend") as factory, \
                     patch.object(mimir, "JarvisMemory") as memory, redirect_stdout(progress):
                    with self.assertRaises(ConfigurationRequired):
                        await mimir.run_mimir("objective", progress_format="jsonl")
                factory.assert_not_called()
                memory.assert_not_called()
                self.assertEqual(json.loads(progress.getvalue())["event"], "configuration_required")


if __name__ == "__main__":
    unittest.main()
