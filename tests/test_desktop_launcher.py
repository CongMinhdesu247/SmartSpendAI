import unittest
from unittest.mock import Mock, MagicMock, patch

import desktop_launcher as launcher


class DesktopStartupTests(unittest.TestCase):
    def test_open_port_without_app_identity_is_not_ready(self):
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.status = 200; response.headers = {}
        with patch.object(launcher, 'build_opener', return_value=opener):
            self.assertFalse(launcher.wait_for_server_ready(timeout=0.01))
            response.headers = {'X-SmartSpend-App': '1'}
            self.assertTrue(launcher.wait_for_server_ready(timeout=0.01))

    def test_failed_or_not_started_server_is_not_ready(self):
        with patch.object(launcher, 'build_opener') as opener:
            self.assertFalse(launcher.wait_for_server_ready(server=Mock(started=False), timeout=0.01))
            opener.return_value.open.assert_not_called()
            self.assertFalse(launcher.wait_for_server_ready(thread=Mock(is_alive=lambda: False), timeout=1))
