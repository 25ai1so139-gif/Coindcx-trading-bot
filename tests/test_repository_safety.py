"""Repository hygiene checks; paths and placeholder names only, never secret values."""

import subprocess
import unittest
from dataclasses import fields
from pathlib import Path

from config import Settings

ROOT = Path(__file__).resolve().parents[1]


class RepositorySafetyTests(unittest.TestCase):
    def test_env_variants_and_common_secret_paths_are_ignored(self):
        for path in (".env", ".env.local", ".env.production", "nested/.env", "nested/.env.local",
                     "secrets.json", "credentials.json", "secrets/token.txt", "credentials/token.txt",
                     "private.pem", "private.key"):
            result = subprocess.run(["git", "check-ignore", "--no-index", "-q", path],
                                    cwd=ROOT, capture_output=True)
            with self.subTest(path=path):
                self.assertEqual(result.returncode, 0)

    def test_env_example_contains_exactly_blank_setting_placeholders(self):
        lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        expected = {f"BOT_{field.name.upper()}=" for field in fields(Settings)}
        self.assertEqual(set(lines), expected)
        self.assertEqual(len(lines), len(expected))
        ignored = subprocess.run(["git", "check-ignore", "--no-index", "-q", ".env.example"],
                                 cwd=ROOT, capture_output=True)
        self.assertEqual(ignored.returncode, 1)

    def test_no_env_or_common_secret_files_are_tracked(self):
        result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True,
                                capture_output=True, text=True)
        for name in result.stdout.split("\0"):
            if not name:
                continue
            path = Path(name)
            with self.subTest(path=name):
                self.assertFalse(path.name == ".env" or (
                    path.name.startswith(".env.") and path.name != ".env.example"))
                self.assertFalse(any(part in {"secrets", "credentials"} for part in path.parts))
                self.assertFalse(path.name.startswith(("secrets.", "credentials.")))
                self.assertNotIn(path.suffix, {".pem", ".key"})
