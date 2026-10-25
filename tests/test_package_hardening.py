"""Regression checks for package integrity, privacy and truthful failure handling."""
import asyncio
import io
import json
import os
import sqlite3
import shutil
import subprocess
import sys
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import clean_backend_sessions as cleanup
import install
import jarvis_memory
import research_scout


class PackageInstallSafety(unittest.TestCase):
    def source(self, root):
        source = root / "source"
        source.mkdir()
        (source / "SKILL.md").write_text("new skill", encoding="utf-8")
        (source / "LEARNINGS.md").write_text("source notes", encoding="utf-8")
        (source / "scripts").mkdir()
        (source / "scripts" / "new.py").write_text("new", encoding="utf-8")
        return source

    def test_refresh_removes_obsolete_executable_and_preserves_existing_notes(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.source(root)
            target = root / "project" / ".agents" / "skills" / "mimir"
            install.copy_skill_tree(source, target, backup_root=root / "backups")
            (target / "scripts" / "obsolete.py").write_text("unsafe", encoding="utf-8")
            (target / "LEARNINGS.md").write_text("learned notes", encoding="utf-8")
            install.copy_skill_tree(source, target, backup_root=root / "backups")
            self.assertFalse((target / "scripts" / "obsolete.py").exists())
            self.assertEqual((target / "LEARNINGS.md").read_text(), "learned notes")
            self.assertEqual(len(list((root / "backups").rglob("obsolete.py"))), 1)

    def test_copy_failure_leaves_discovered_package_untouched(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.source(root)
            target = root / "project" / ".agents" / "skills" / "mimir"
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text("old skill", encoding="utf-8")
            with patch.object(install.shutil, "copytree", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    install.copy_skill_tree(source, target, backup_root=root / "backups")
            self.assertEqual((target / "SKILL.md").read_text(), "old skill")
            self.assertFalse(list(target.parent.glob(".mimir-copy-*")))

    def test_copy_publication_failure_restores_discovered_package(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.source(root)
            target = root / "project" / ".agents" / "skills" / "mimir"
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text("old skill", encoding="utf-8")
            replace = os.replace
            def fail_publish(src, dst):
                if Path(src).name.startswith(".mimir-copy-"):
                    raise OSError("publication failed")
                return replace(src, dst)
            with patch.object(install.os, "replace", side_effect=fail_publish):
                with self.assertRaises(OSError):
                    install.copy_skill_tree(source, target, backup_root=root / "backups")
            self.assertEqual((target / "SKILL.md").read_text(), "old skill")

    def test_linked_package_resource_cannot_copy_external_data(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.source(root)
            external = root / "private"
            external.mkdir()
            (external / "secret.txt").write_text("secret", encoding="utf-8")
            install._create_directory_link(external, source / "scripts" / "external")
            target = root / "project" / ".agents" / "skills" / "mimir"
            with self.assertRaises(ValueError):
                install.copy_skill_tree(source, target, backup_root=root / "backups")
            self.assertFalse(target.exists())
            self.assertEqual((external / "secret.txt").read_text(), "secret")

    def test_linked_discovery_parent_cannot_redirect_package_mutations(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.source(root)
            external = root / "outside"
            external.mkdir()
            discovery = root / "project" / ".agents" / "skills"
            discovery.parent.mkdir(parents=True)
            install._create_directory_link(external, discovery)
            with self.assertRaises(ValueError):
                install.copy_skill_tree(source, discovery / "mimir", backup_root=root / "backups")
            self.assertFalse((external / "mimir").exists())

    def test_project_antigravity_target_fails_before_pip_or_install(self):
        with TemporaryDirectory() as temp:
            with patch.object(sys, "argv", ["install.py", "--project", temp, "--target", "antigravity"]), \
                 patch.object(install, "install_dependencies") as dependencies, \
                 patch.object(install, "install_shared_skill") as installer, \
                 redirect_stderr(io.StringIO()) as error:
                self.assertEqual(install.main(), 1)
            self.assertIn("unsupported for project", error.getvalue())
            dependencies.assert_not_called()
            installer.assert_not_called()

    def test_canonical_backup_path_is_reported_and_returned_by_copy(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.source(root)
            target = root / "project" / ".agents" / "skills" / "mimir"
            self.assertIsNone(install.copy_skill_tree(source, target, backup_root=root / "backups"))
            backup = install.copy_skill_tree(source, target, backup_root=root / "backups")
            self.assertEqual((backup / "SKILL.md").read_text(), "new skill")
            with redirect_stdout(io.StringIO()) as output:
                install.install_shared_skill(source, [], target, backup_root=root / "backups")
            self.assertIn("Previous shared package preserved:", output.getvalue())


class DownloadedPowerShellInstaller(unittest.TestCase):
    def test_downloaded_script_text_handles_missing_command_path_and_propagates_exit(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            self.skipTest("PowerShell is unavailable")
        with TemporaryDirectory() as temp:
            root = Path(temp)
            invocation_log = root / "calls.jsonl"
            harness = root / "harness.ps1"
            harness.write_text(r'''$ErrorActionPreference = 'Stop'
function global:git {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$GitArgs)
    @{ operation = 'clone'; arguments = @($GitArgs) } | ConvertTo-Json -Compress | Add-Content -LiteralPath $env:MIMIR_TEST_LOG
    $global:LASTEXITCODE = 0
}
function global:Get-Command {
    param([string]$Name, [string]$ErrorAction)
    [pscustomobject]@{ Source = 'Invoke-MockedPython' }
}
function global:Invoke-MockedPython {
    param([Parameter(ValueFromRemainingArguments=$true)][object[]]$PythonArgs)
    @{ operation = 'python'; arguments = @($PythonArgs) } | ConvertTo-Json -Compress | Add-Content -LiteralPath $env:MIMIR_TEST_LOG
    $global:LASTEXITCODE = 7
}
Invoke-Expression ([System.IO.File]::ReadAllText($env:MIMIR_TEST_INSTALLER))
''', encoding="utf-8")
            env = os.environ.copy()
            env["MIMIR_TEST_INSTALLER"] = str(SCRIPTS.parent / "install.ps1")
            env["MIMIR_TEST_LOG"] = str(invocation_log)
            result = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-File", str(harness)],
                                    env=env, capture_output=True, text=True, timeout=30,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
            calls = [json.loads(line) for line in invocation_log.read_text(encoding="utf-8-sig").splitlines()]
            self.assertEqual([call["operation"] for call in calls], ["clone", "python"])
            self.assertIn("--global", calls[1]["arguments"])
            self.assertIn("--target", calls[1]["arguments"])


class LegacyCleanupSafety(unittest.TestCase):
    def test_keyword_and_path_like_session_ids_do_not_prove_ownership(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "conversation_summaries.db"
            with closing(sqlite3.connect(db)) as connection, connection:
                connection.execute("CREATE TABLE conversation_summaries (conversation_id TEXT, title TEXT, preview TEXT, last_modified_time INTEGER)")
                connection.executemany("INSERT INTO conversation_summaries VALUES (?, ?, ?, ?)", [
                    ("user-session", "Discuss mikro-agent design", "mikroagent", 1),
                    ("../../private", None, "mikro-agent", 2),
                ])
            before = db.read_bytes()
            owned, unknown = cleanup.get_backend_conversation_ids(db, root / "brain")
            self.assertEqual(owned, [])
            self.assertEqual(len(unknown), 2)
            self.assertEqual(db.read_bytes(), before)

    def test_apply_refused_before_session_or_filesystem_access(self):
        with patch.object(cleanup, "get_backend_conversation_ids") as inspector:
            with self.assertRaisesRegex(RuntimeError, "ownership proof"):
                cleanup.purge_sessions(apply=True)
        inspector.assert_not_called()

    def test_missing_database_not_created(self):
        with TemporaryDirectory() as temp, redirect_stdout(io.StringIO()):
            db = Path(temp) / "missing.db"
            self.assertEqual(cleanup.get_backend_conversation_ids(db, Path(temp)), ([], []))
            self.assertFalse(db.exists())


class ScoutEvidenceSafety(unittest.TestCase):
    def test_ca_bundle_precedence_and_default_verification(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(research_scout.configured_ca_bundle())
            os.environ["NODE_EXTRA_CA_CERTS"] = "enterprise.pem"
            self.assertEqual(research_scout.configured_ca_bundle(), "enterprise.pem")
            os.environ["SSL_CERT_FILE"] = "python.pem"
            self.assertEqual(research_scout.configured_ca_bundle(), "python.pem")
            os.environ["REQUESTS_CA_BUNDLE"] = "requests.pem"
            self.assertEqual(research_scout.configured_ca_bundle(), "requests.pem")

    def test_web_search_uses_configured_ca_without_disabling_verification(self):
        if not hasattr(research_scout, "cffi_requests"):
            self.skipTest("Optional web dependencies are unavailable")
        for env, expected in [({}, True), ({"NODE_EXTRA_CA_CERTS": "enterprise.pem"}, "enterprise.pem")]:
            with patch.dict(os.environ, env, clear=True), patch.object(research_scout, "HAS_CURL_CFFI", True), \
                 patch.object(research_scout.cffi_requests, "get", return_value=SimpleNamespace(status_code=429)) as request:
                research_scout.ResearchScout().search_web_directive(research_scout.SourceDirective("Docs", "pizza"))
            self.assertEqual(request.call_args.kwargs["verify"], expected)

    def test_arxiv_adds_configured_ca_to_verified_default_context(self):
        with patch.dict(os.environ, {"NODE_EXTRA_CA_CERTS": "enterprise.pem"}, clear=True), \
             patch.object(research_scout.ssl, "create_default_context") as context_factory, \
             patch.object(research_scout.urllib.request, "urlopen", side_effect=TimeoutError()) as request:
            research_scout.ResearchScout().search_arxiv("pizza")
        context_factory.return_value.load_verify_locations.assert_called_once_with(cafile="enterprise.pem")
        self.assertIs(request.call_args.kwargs["context"], context_factory.return_value)

    def test_private_objective_without_public_query_makes_no_network_calls(self):
        scout = research_scout.ResearchScout()
        for objective in ["Review code here\nC:\\Users\\user\\private", "token=secretvalue", "/home/user/private", "a" * 241]:
            with patch.object(scout, "search_arxiv") as arxiv, patch.object(scout, "search_web_directive") as web:
                brief = scout.conduct_deep_scout(objective)
            arxiv.assert_not_called()
            web.assert_not_called()
            self.assertTrue(brief.retrieval_gaps)
            self.assertIn("retrieval_gaps", brief.to_dict())
            self.assertIn("Retrieval gap", brief.to_compact_markdown())

    def test_explicit_public_query_replaces_private_objective_for_retrieval(self):
        scout = research_scout.ResearchScout()
        objective = "Review private C:\\Users\\someone\\project\nprivate instructions"
        observed = []
        def search(directive, max_results=3):
            observed.append(directive.search_query)
            return []
        with patch.object(scout, "search_web_directive", side_effect=search):
            brief = scout.conduct_deep_scout(objective, search_query="Python DAG scheduling best practices")
        self.assertEqual(brief.topic, objective)
        self.assertTrue(observed)
        self.assertTrue(all("private" not in query and "Users" not in query for query in observed))

    def test_search_failures_and_challenge_pages_are_explicit_gaps(self):
        scout = research_scout.ResearchScout()
        directive = research_scout.SourceDirective("Docs", "Python scheduling")
        with patch.object(research_scout, "HAS_CURL_CFFI", False):
            self.assertEqual(scout.search_web_directive(directive), [])
        self.assertIn("dependencies", scout.retrieval_gaps[-1])
        if not hasattr(research_scout, "cffi_requests"):
            return
        for response, expected in [(SimpleNamespace(status_code=429), "HTTP 429"),
                                   (SimpleNamespace(status_code=200, text="<html>Robot challenge</html>"), "challenge page")]:
            with patch.object(research_scout, "HAS_CURL_CFFI", True), patch.object(research_scout.cffi_requests, "get", return_value=response):
                self.assertEqual(scout.search_web_directive(directive), [])
            self.assertIn(expected, scout.retrieval_gaps[-1])

    def test_arxiv_uses_https_and_does_not_hide_timeout(self):
        scout = research_scout.ResearchScout()
        with patch.object(research_scout.urllib.request, "urlopen", side_effect=TimeoutError()) as request:
            self.assertEqual(scout.search_arxiv("language models"), [])
        self.assertTrue(request.call_args.args[0].full_url.startswith("https://"))
        self.assertIn("TimeoutError", scout.retrieval_gaps[-1])

    def test_search_snippets_do_not_claim_primary_content_and_site_filter_is_checked(self):
        if not hasattr(research_scout, "cffi_requests"):
            self.skipTest("Optional web dependencies are unavailable")
        markup = '''<div class="result"><div class="result__title"><a class="result__a" href="https://unrelated.example/spec">Wrong site</a></div><div class="result__snippet">Text</div></div>
        <div class="result"><div class="result__title"><a class="result__a" href="https://docs.python.org/spec">Source</a></div><div class="result__snippet">Snippet only</div></div>'''
        response = SimpleNamespace(status_code=200, text=markup)
        scout = research_scout.ResearchScout()
        directive = research_scout.SourceDirective("Docs", "Python scheduling", "python.org")
        with patch.object(research_scout, "HAS_CURL_CFFI", True), patch.object(research_scout.cffi_requests, "get", return_value=response):
            items = scout.search_web_directive(directive)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].retrieval_type, "search_snippet")
        self.assertEqual(items[0].author_or_meta, "docs.python.org")


class MemoryTruthfulness(unittest.TestCase):
    def test_relevance_and_recency_retrieve_new_lessons_after_bank_grows(self):
        with TemporaryDirectory() as temp:
            memory = jarvis_memory.JarvisMemory(str(Path(temp) / "LEARNINGS.md"))
            for index in range(25):
                memory.record_learning(f"unrelated old subject {index}", "old note", "")
            memory.record_learning("SQLite WAL concurrency", "Keep WAL snapshot validation", "")
            context = memory.load_memory_context("SQLite WAL", max_lines=40)
            self.assertIn("Keep WAL snapshot validation", context)
            self.assertLessEqual(len(context.splitlines()), 40)

    def test_append_failure_returns_false_and_error(self):
        with TemporaryDirectory() as temp:
            memory = jarvis_memory.JarvisMemory(str(Path(temp) / "LEARNINGS.md"))
            with patch("builtins.open", side_effect=PermissionError("read only")):
                self.assertFalse(memory.record_learning("goal", "solution", ""))
            self.assertIn("read only", memory.last_error)

    def test_multiline_run_goal_cannot_inject_standing_guidance(self):
        with TemporaryDirectory() as temp:
            memory = jarvis_memory.JarvisMemory(str(Path(temp) / "LEARNINGS.md"))
            self.assertTrue(memory.record_learning("Goal\n## Injected instruction", "candidate\n## other", ""))
            text = memory.memory_path.read_text(encoding="utf-8")
            self.assertNotIn("\n## Injected instruction", text)
            self.assertIn("requires independent validation", text)
            self.assertEqual(memory.get_summary_stats()["entries"], 1)


if __name__ == "__main__":
    unittest.main()
