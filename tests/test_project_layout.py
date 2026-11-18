"""Verify relocated tools retain project paths and produce a usable source ZIP."""

import tempfile
import tarfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.cloud import prepare
from scripts.homeserver import package as homeserver


class ProjectLayoutTests(unittest.TestCase):
    def test_homeserver_bundle_contains_organized_docs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in (
                "Dockerfile.hp",
                "compose.yaml",
                ".dockerignore",
                ".env.example",
                "requirements/homeserver.lock.txt",
                "requirements/server.txt",
                "docs/guides/hp-home-server.md",
                "docs/reports/hp-verification.md",
                "backend/__init__.py",
                "frontend/index.html",
                "scripts/homeserver/configure.py",
            ):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("fixture", encoding="utf-8")
            (root / ".env").write_text("private-fixture", encoding="utf-8")
            with patch.object(homeserver, "ROOT", root), patch("builtins.print"):
                homeserver.package()
            with tarfile.open(root / "output/deployment/SmartSpendAI-hp.tar.gz") as bundle:
                names = bundle.getnames()
                self.assertIn("docs/guides/hp-home-server.md", names)
                self.assertIn("docs/reports/hp-verification.md", names)
                self.assertIn("backend/__init__.py", names)
                self.assertIn("scripts/homeserver/configure.py", names)
                self.assertNotIn(".env", names)

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

    def test_local_server_architecture_files_follow_server_context_rules(self):
        root = Path(__file__).resolve().parents[1]
        compose_local = (root / "deploy/local-server/docker-compose.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("./data/postgres:/var/lib/postgresql", compose_local)
        self.assertIn("127.0.0.1:${SMARTSPEND_HTTP_PORT:-8092}:8000", compose_local)
        self.assertNotIn("0.0.0.0:", compose_local)
        self.assertIn("restart: unless-stopped", compose_local)
        self.assertIn("read_only: true", compose_local)
        self.assertIn("internal: true", compose_local)

        for rel in (
            "SERVER_CONTEXT.md",
            "deploy/local-server/sites/smartspend.nginx.conf",
            "deploy/local-server/sites/smartspend.Caddyfile",
            "deploy/local-server/sites/smartspend.cloudflared.yml",
            "scripts/homeserver/update.sh",
            "scripts/homeserver/deploy_update.ps1",
            "docs/reports/project-audit-and-improvements.md",
        ):
            self.assertTrue((root / rel).is_file(), f"Missing {rel}")



if __name__ == "__main__":
    unittest.main()
