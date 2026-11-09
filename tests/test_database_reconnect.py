import os
import unittest
from unittest.mock import Mock, patch

from backend import database


class ReconnectTests(unittest.TestCase):
    def test_failed_desktop_connection_retains_engine_config_and_never_falls_back(self):
        old, candidate = Mock(), Mock()
        with (
            patch.dict(os.environ, {"SMARTSPEND_CLOUD": "0"}),
            patch.object(database, "engine", old),
            patch.object(database, "create_engine", return_value=candidate),
            patch(
                "backend.account_migration.require_ready",
                side_effect=RuntimeError("missing migration"),
            ) as ready,
            patch.object(database, "save_config") as save,
            patch.object(database, "_init_sqlite_fallback") as fallback,
        ):
            with self.assertRaises(database.DatabaseConnectionError):
                database.init_db_connection(
                    "postgresql://owner:secret@example.invalid/db", config_to_save={}
                )
            self.assertIs(database.engine, old)
            old.dispose.assert_not_called()
            candidate.dispose.assert_called_once()
            ready.assert_called_once_with(candidate)
            save.assert_not_called()
            fallback.assert_not_called()

    def test_invalid_database_url_does_not_select_local_database(self):
        with (
            patch.dict(os.environ, {"SMARTSPEND_CLOUD": "0"}),
            patch.object(database, "_create_sqlite_engine") as local,
        ):
            with self.assertRaises(database.DatabaseConnectionError):
                database.init_db_connection("not-a-postgres-url")
            local.assert_not_called()

    def test_config_save_failure_does_not_swap_live_engine(self):
        old, candidate = Mock(), Mock()
        with (
            patch.dict(os.environ, {"SMARTSPEND_CLOUD": "0"}),
            patch.object(database, "engine", old),
            patch.object(database, "create_engine", return_value=candidate),
            patch("backend.account_migration.require_ready"),
            patch("backend.finance_api.initialize_finance"),
            patch.object(database, "save_config", side_effect=OSError("disk full")),
        ):
            with self.assertRaises(database.DatabaseConnectionError):
                database.init_db_connection(
                    "postgresql://owner:secret@example.invalid/db", config_to_save={}
                )
            self.assertIs(database.engine, old)
            old.dispose.assert_not_called()
            candidate.dispose.assert_called_once()
