"""Private setup must preserve Argon2 dollar signs and refuse secret regeneration."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pwdlib import PasswordHash
from scripts.homeserver import configure


class HPSetupTests(unittest.TestCase):
    def test_generated_env_verifies_password_and_cannot_overwrite_existing_db_secret(self):
        password = "Isolated-Setup-Password-12345"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text("SMARTSPEND_DB_PASSWORD=\nGEMINI_MODEL=\n", encoding="utf-8")
            with (
                patch("sys.argv", ["configure.py", "--path", str(path)]),
                patch("builtins.input", side_effect=["8092", "https://smartspend.test"]),
                patch("getpass.getpass", side_effect=[password, password, ""]),
                patch("builtins.print"),
            ):
                configure.main()
            content = path.read_text(encoding="utf-8")
            values = dict(line.split("=", 1) for line in content.splitlines())
            hashed = values["SMARTSPEND_PASSWORD_HASH"]
            self.assertTrue(hashed.startswith("'$argon2id$"))
            self.assertTrue(PasswordHash.recommended().verify(password, hashed[1:-1]))
            self.assertNotIn(password, content)
            with (
                patch("sys.argv", ["configure.py", "--path", str(path)]),
                self.assertRaises(SystemExit),
            ):
                configure.main()
            self.assertEqual(path.read_text(encoding="utf-8"), content)


if __name__ == "__main__":
    unittest.main()
