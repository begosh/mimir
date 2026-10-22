"""Installation behavior: one package, shared updates, safe migration and failure."""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import install


class SharedInstallation(unittest.TestCase):
    def fixture(self, root):
        source = root / "source"
        source.mkdir()
        for name, content in (("SKILL.md", "skill v1"), ("LEARNINGS.md", "source notes")):
            (source / name).write_text(content)
        for directory in ("scripts", "prompts", "docs"):
            (source / directory).mkdir()
            (source / directory / "fixture.txt").write_text(directory)
        return source

    def test_one_package_all_links_share_updates_and_preserve_notes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.fixture(root)
            project = root / "project"
            canonical = install.shared_skill_path(project)
            targets = install.get_project_targets(project)
            with redirect_stdout(io.StringIO()):
                install.install_shared_skill(source, targets, canonical)
            for _, target in targets:
                self.assertEqual(target.resolve(), canonical.resolve())
                self.assertTrue((target / "docs/fixture.txt").exists())
            (canonical / "LEARNINGS.md").write_text("learned after installation")
            (source / "SKILL.md").write_text("skill v2")
            with redirect_stdout(io.StringIO()):
                backups = install.install_shared_skill(source, targets, canonical)
            self.assertEqual(backups, [])
            for _, target in targets:
                self.assertEqual((target / "SKILL.md").read_text(), "skill v2")
                self.assertEqual((target / "LEARNINGS.md").read_text(), "learned after installation")

    def test_migrate_copy_keeps_old_resources_outside_discovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.fixture(root)
            canonical = install.shared_skill_path(root)
            install.copy_skill_tree(source, canonical)
            destination = root / ".claude/skills/mimir"
            destination.mkdir(parents=True)
            (destination / "LEARNINGS.md").write_text("separate historical notes")
            backup = install.link_skill_tree(canonical, destination, root / ".mimir/install-backups")
            self.assertEqual(destination.resolve(), canonical.resolve())
            self.assertEqual((backup / "LEARNINGS.md").read_text(), "separate historical notes")
            self.assertNotIn("skills", backup.parts[len(root.parts):])

    def test_link_creation_failure_leaves_old_copy_and_source_intact(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.fixture(root)
            destination = root / ".claude/skills/mimir"
            destination.mkdir(parents=True)
            (destination / "SKILL.md").write_text("existing")
            with patch.object(install, "_create_directory_link", side_effect=OSError("link failed")):
                with self.assertRaises(OSError):
                    install.link_skill_tree(source, destination)
            self.assertEqual((destination / "SKILL.md").read_text(), "existing")
            self.assertEqual((source / "SKILL.md").read_text(), "skill v1")

    def test_replacement_failure_restores_copy_without_deleting_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.fixture(root)
            destination = root / ".claude/skills/mimir"
            destination.mkdir(parents=True)
            (destination / "SKILL.md").write_text("existing")
            replace = os.replace
            def failing_replace(src, dst):
                if Path(src).name.startswith(".mimir-link-"):
                    raise OSError("replacement failed")
                return replace(src, dst)
            with patch.object(install.os, "replace", side_effect=failing_replace):
                with self.assertRaises(OSError):
                    install.link_skill_tree(source, destination, root / "backups")
            self.assertEqual((destination / "SKILL.md").read_text(), "existing")
            self.assertTrue((source / "SKILL.md").exists())
            self.assertFalse(any(destination.parent.glob(".mimir-link-*")))

    def test_existing_external_link_replaced_without_touching_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.fixture(root)
            external = root / "external"
            external.mkdir()
            (external / "SKILL.md").write_text("external")
            destination = root / ".claude/skills/mimir"
            destination.parent.mkdir(parents=True)
            install._create_directory_link(external, destination)
            install.link_skill_tree(source, destination, root / "backups")
            self.assertEqual(destination.resolve(), source.resolve())
            self.assertEqual((external / "SKILL.md").read_text(), "external")

    def test_invalid_destination_rejected_before_moving_anything(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.fixture(root)
            with self.assertRaises(ValueError):
                install.link_skill_tree(source, root)
            self.assertTrue(source.exists())

    def test_developer_link_and_return_to_copy_preserve_source_notes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.fixture(root)
            canonical = install.shared_skill_path(root)
            install.copy_skill_tree(source, canonical, use_link=True)
            self.assertEqual(canonical.resolve(), source.resolve())
            install.copy_skill_tree(source, canonical)
            self.assertNotEqual(canonical.resolve(), source.resolve())
            self.assertEqual((canonical / "LEARNINGS.md").read_text(), "source notes")
            self.assertTrue((source / "SKILL.md").is_file())

    def test_project_install_inside_checkout_does_not_copy_itself(self):
        with tempfile.TemporaryDirectory() as temp:
            source = self.fixture(Path(temp))
            canonical = install.shared_skill_path(source)
            install.copy_skill_tree(source, canonical)
            self.assertTrue((canonical / "scripts/fixture.txt").exists())
            self.assertFalse((canonical / ".agents").exists())

    def test_target_filter_installs_shared_package_and_selected_link(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.fixture(root)
            project = root / "project"
            with patch.object(install, "REPO_ROOT", source), patch.object(sys, "argv", [
                "install.py", "--project", str(project), "--target", "claude", "--skip-pip"
            ]), redirect_stdout(io.StringIO()):
                self.assertEqual(install.main(), 0)
            canonical = install.shared_skill_path(project)
            self.assertEqual((project / ".claude/skills/mimir").resolve(), canonical.resolve())
            self.assertFalse((project / ".codex/skills/mimir").exists())

    def test_failure_returns_nonzero_instead_of_success_summary(self):
        with patch.object(sys, "argv", ["install.py", "--skip-pip"]), \
             patch.object(install, "install_shared_skill", side_effect=OSError("junction unavailable")), \
             redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            self.assertEqual(install.main(), 1)
        self.assertNotIn("Installation complete", out.getvalue())
        self.assertIn("junction unavailable", err.getvalue())


if __name__ == "__main__":
    unittest.main()
