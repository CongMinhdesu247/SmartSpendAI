import os
import unittest
from unittest.mock import Mock, patch
from backend import ai_service
from backend.ai_limits import AILimiter
from fastapi import HTTPException


class SharedAITests(unittest.TestCase):
    def test_configured_model_is_the_only_model_called(self):
        client = Mock()
        with (
            patch.dict(os.environ, {"GEMINI_MODEL": "owner-selected-model"}),
            patch.object(ai_service, "_parse_ai_response", return_value="parsed"),
        ):
            self.assertEqual(
                ai_service._call_gemini_with_fallback(client, "prompt", "system"), "parsed"
            )
        self.assertEqual(
            client.models.generate_content.call_args.kwargs["model"], "owner-selected-model"
        )
        client.models.list.assert_not_called()

    def test_pinned_model_failure_does_not_switch_models_or_expose_provider_error(self):
        client = Mock()
        client.models.generate_content.side_effect = RuntimeError("404 provider-private-credential")
        with patch.dict(os.environ, {"GEMINI_MODEL": "owner-selected-model"}):
            with self.assertRaises(RuntimeError) as error:
                ai_service._call_gemini_with_fallback(client, "prompt", "system")
        self.assertNotIn("provider-private-credential", str(error.exception))
        self.assertEqual(client.models.generate_content.call_count, 1)
        client.models.list.assert_not_called()

    def test_quota_timeout_and_auth_fail_without_switching_models(self):
        for code in (429, 403, 503, None):
            error = RuntimeError("private-provider-response")
            error.code = code
            client = Mock()
            client.models.generate_content.side_effect = error
            with patch.dict(os.environ, {"GEMINI_MODEL": ""}):
                with self.assertRaises(RuntimeError):
                    ai_service._call_gemini_with_fallback(client, "prompt", "system")
            self.assertEqual(client.models.generate_content.call_count, 1)
            client.models.list.assert_not_called()

    def test_only_missing_model_falls_back_with_bounded_attempts(self):
        error = RuntimeError("model unavailable")
        error.code = 404
        client = Mock()
        client.models.generate_content.side_effect = error
        with patch.dict(os.environ, {"GEMINI_MODEL": ""}):
            with self.assertRaises(RuntimeError):
                ai_service._call_gemini_with_fallback(client, "prompt", "system")
        self.assertEqual(
            client.models.generate_content.call_count, len(ai_service.PREFERRED_MODELS)
        )
        client.models.list.assert_not_called()

    def test_ai_limits_concurrency_user_quota_and_expiry(self):
        limiter = AILimiter(per_minute=1, concurrent=1)
        with patch("backend.ai_limits.time.monotonic", return_value=1):
            limiter.acquire("alice")
            with self.assertRaises(HTTPException):
                limiter.acquire("bob")
            limiter.slots.release()
            with self.assertRaises(HTTPException):
                limiter.acquire("alice")
            limiter.acquire("bob")
            limiter.slots.release()
        with patch("backend.ai_limits.time.monotonic", return_value=62):
            limiter.acquire("alice")
            limiter.slots.release()


if __name__ == "__main__":
    unittest.main()
