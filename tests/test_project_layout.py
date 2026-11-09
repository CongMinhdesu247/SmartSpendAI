"""Verify relocated tools retain project paths and produce a usable source ZIP."""

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.cloud import prepare


class ProjectLayoutTests(unittest.TestCase):
    def test_cloud_paths_still_point_to_project_root(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(prepare.ROOT, root)
        self.assertEqual(prepare.ENV_FILE, root / ".env.cloud")
        self.assertEqual(prepare.OUTPUT, root / "output" / "deployment")

    def test_cloud_bundle_contains_relocated_server_requirements(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in (
                "Dockerfile",
                ".dockerignore",
                "render.yaml",
                "requirements/server.txt",
                "backend/__init__.py",
                "frontend/index.html",
            ):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("fixture", encoding="utf-8")
            with (
                patch.object(prepare, "ROOT", root),
                patch.object(prepare, "ENV_FILE", root / ".env.cloud"),
                patch.object(prepare, "OUTPUT", root / "output" / "deployment"),
                patch.object(
                    prepare,
                    "load_config",
                    return_value={
                        "database_url": "postgresql://fixture:fixture@localhost/fixture",
                        "gemini_api_key": "disposable-fixture-key",
                    },
                ),
                patch.object(
                    prepare,
                    "read_env",
                    return_value={
                        "SMARTSPEND_PASSWORD_HASH": "disposable-fixture-hash",
                        "SMARTSPEND_SESSION_SECRET": "disposable-fixture-session-secret",
                    },
                ),
                patch("builtins.print"),
            ):
                prepare.prepare()
            with zipfile.ZipFile(root / "output/deployment/SmartSpend-cloud-source.zip") as bundle:
                self.assertIn("requirements/server.txt", bundle.namelist())
                self.assertIn("Dockerfile", bundle.namelist())
                self.assertIn("backend/__init__.py", bundle.namelist())
                self.assertIn("frontend/index.html", bundle.namelist())
                self.assertNotIn(".env.cloud", bundle.namelist())


if __name__ == "__main__":
    unittest.main()
