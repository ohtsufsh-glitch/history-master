"""Issue #54: 標準ライブラリだけの更新・PR判定テスト。一時Gitリポジトリを使用。"""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bump_app_version as bump
import check_app_version as check


def html(version):
    return f'<script>\nconst APP_VERSION = "{version}";\n</script>\n'


class BumpVersionTest(unittest.TestCase):
    def test_patch_and_explicit_version_preserve_every_other_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.html"
            original = (
                "<p>表示</p>\r\nconst APP_VERSION = 'v1.7.9'; // アプリ版\r\n"
                "const DB_VERSION = 9;\r\nconst BACKUP_VERSION = 9;\r\n"
                "const question = {schemaVersion:1};\r\n"
            ).encode("utf-8")
            path.write_bytes(original)
            self.assertEqual(bump.bump_file(path), ("v1.7.9", "v1.7.10"))
            self.assertEqual(path.read_bytes(), original.replace(b"v1.7.9", b"v1.7.10"))
            self.assertEqual(bump.bump_file(path, "v1.8.0"), ("v1.7.10", "v1.8.0"))
            self.assertEqual(path.read_bytes(), original.replace(b"v1.7.9", b"v1.8.0"))

    def test_invalid_or_ambiguous_definition_never_writes(self):
        cases = [
            "<p>missing</p>", html("v1.7.3") * 2,
            html("v1.7.3") + 'let APP_VERSION = "v1.7.4";\n',
            html("v1.7.3") + 'APP_VERSION = "v1.7.4";\n',
            html("v1.7.3").replace("const", "let"),
            html("v1.7.3").replace('"v1.7.3"', '"v1.7.3" + "bad"'),
            *[html(value) for value in ("1.7.3", "v01.7.3", "v1.7", "v1.7.3-beta", "v1.7.3+build", "v1.7.x", "")],
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.html"
            for source in cases:
                with self.subTest(source=source):
                    original = source.encode("utf-8")
                    path.write_bytes(original)
                    with self.assertRaises(bump.VersionError):
                        bump.bump_file(path)
                    self.assertEqual(path.read_bytes(), original)

    def test_invalid_same_or_older_target_never_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.html"
            original = html("v1.7.3").encode("utf-8")
            path.write_bytes(original)
            for version in ("v1.7.3", "v1.7.2", "v1.6.99", "v0.99.99", "1.8.0", "v1.08.0", "v1.8.0-rc1"):
                with self.subTest(version=version), self.assertRaises(bump.VersionError):
                    bump.bump_file(path, version)
                self.assertEqual(path.read_bytes(), original)


class CheckVersionTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.run_git("init", "-q")
        self.run_git("config", "user.name", "Version test")
        self.run_git("config", "user.email", "version-test@example.invalid")
        self.base = self.commit({"index.html": html("v1.7.3"), "assets/card.webp": "fixture"})
        self.patcher = patch.object(check, "ROOT", self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def run_git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()

    def commit(self, files):
        for name, content in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if content is None:
                path.unlink()
            else:
                path.write_text(content, encoding="utf-8")
        self.run_git("add", ".")
        self.run_git("commit", "-qm", "version fixture")
        return self.run_git("rev-parse", "HEAD")

    def test_app_change_requires_valid_strictly_larger_version(self):
        for version, succeeds in (("v1.7.3", False), ("v1.7.2", False), ("v1.6.99", False),
                                  ("v1.7.4", True), ("v1.7.10", True), ("v1.8.0", True),
                                  ("v2.0.0", True), ("v01.8.0", False), ("v1.8.0-rc1", False)):
            with self.subTest(version=version):
                self.run_git("reset", "--hard", self.base)
                head = self.commit({"index.html": html(version) + "<!-- app change -->\n"})
                if succeeds:
                    self.assertIn("OK:", check.check_versions(self.base, head))
                else:
                    with self.assertRaises(bump.VersionError):
                        check.check_versions(self.base, head)

    def test_missing_duplicate_or_malformed_definition_fails(self):
        for source in ("<p>missing</p>", html("v1.7.4") * 2, html("bad")):
            with self.subTest(source=source):
                self.run_git("reset", "--hard", self.base)
                head = self.commit({"index.html": source})
                with self.assertRaises(bump.VersionError):
                    check.check_versions(self.base, head)

    def test_assets_add_modify_delete_and_move_require_bump(self):
        for files in ({"assets/new.webp": "new"}, {"assets/card.webp": "updated"},
                      {"assets/card.webp": None}, {"assets/card.webp": None, "docs/card.webp": "fixture"}):
            with self.subTest(files=files):
                self.run_git("reset", "--hard", self.base)
                head = self.commit(files)
                with self.assertRaises(bump.VersionError):
                    check.check_versions(self.base, head)
        head = self.commit({"assets/new.webp": "new", "index.html": html("v1.7.4")})
        self.assertIn("OK:", check.check_versions(self.base, head))

    def test_runner_add_modify_delete_and_move_require_bump(self):
        runner_base = self.commit({"runner/game.js": "fixture"})
        cases = (
            {"runner/index.html": "new page"},
            {"runner/style.css": "new style"},
            {"runner/patterns.js": "future module"},
            {"runner/assets/character.svg": "future asset"},
            {"runner/game.js": "updated"},
            {"runner/game.js": None},
            {"runner/game.js": None, "docs/game.js": "fixture"},
        )
        for files in cases:
            with self.subTest(files=files):
                self.run_git("reset", "--hard", runner_base)
                head = self.commit(files)
                with self.assertRaises(bump.VersionError):
                    check.check_versions(runner_base, head)
                bumped = self.commit({"index.html": html("v1.7.4")})
                self.assertIn("OK:", check.check_versions(runner_base, bumped))

    def test_docs_tests_and_tools_only_do_not_require_bump_even_when_main_advances(self):
        head = self.commit({name: "fixture" for name in (
            "README.md", "AGENTS.md", "docs/guide.md", "tests/example_test.py",
            "scripts/tool.py", ".github/workflows/check.yml", "assets/empty/.gitkeep",
            "runner/assets/.gitkeep",
        )})
        self.assertIn("版更新は不要", check.check_versions(self.base, head))
        self.run_git("checkout", "--detach", self.base)
        latest_main = self.commit({"index.html": html("v1.7.4"), "assets/new.webp": "main change"})
        self.assertIn("版更新は不要", check.check_versions(latest_main, head))

    def test_parallel_pr_duplicate_compares_against_latest_main_not_ancestor(self):
        head = self.commit({"index.html": html("v1.7.4"), "assets/pr.webp": "PR change"})
        self.assertIn("OK:", check.check_versions(self.base, head))
        self.run_git("checkout", "--detach", self.base)
        latest_main = self.commit({"index.html": html("v1.7.4"), "assets/main.webp": "main change"})
        with self.assertRaises(bump.VersionError):
            check.check_versions(latest_main, head)
        self.run_git("checkout", "--detach", head)
        updated = self.commit({"index.html": html("v1.7.5")})
        self.assertIn("OK:", check.check_versions(latest_main, updated))


if __name__ == "__main__":
    unittest.main()
