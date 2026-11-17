import os
import json
from types import SimpleNamespace
from pydantic import ValidationError
import unittest
from unittest.mock import Mock, patch
from backend import ai_service
from backend.ai_limits import AILimiter
from fastapi import HTTPException


class SharedAITests(unittest.TestCase):
    def test_weekly_plan_deadline_reaches_google_without_automatic_retries(self):
        # Build an SDK HTTP request offline: its header is Google's actual deadline,
        # not just the local socket timeout. No provider call or real key is used.
        with ai_service.make_client("offline-test-not-a-real-key") as client:
            request = client._api_client._build_request(
                "POST", "models/fixture:generateContent", {}
            )
            self.assertEqual(request.headers["X-Server-Timeout"], "90")
            self.assertEqual(client._api_client._http_options.retry_options.attempts, 1)

    def test_provider_schema_is_simple_and_response_still_validated_locally(self):
        valid = {
            "title": "Đi chợ",
            "estimated_cost": 10000,
            "advice": "Mua đủ dùng",
            "items": [
                {
                    "category": "grocery",
                    "time_or_day": "Ngày 1",
                    "name": "Rau",
                    "details": "Rửa sạch",
                    "price": 10000,
                }
            ],
        }
        client = Mock()
        client.models.generate_content.return_value = SimpleNamespace(
            parsed=None, text=json.dumps(valid)
        )
        with patch.dict(os.environ, {"GEMINI_MODEL": "owner-selected-model"}):
            result = ai_service._call_gemini_with_fallback(client, "prompt", "system")
        self.assertEqual(result.items[0].price, 10000)
        config = client.models.generate_content.call_args.kwargs["config"]
        schema = config.response_json_schema
        self.assertIsNone(config.response_schema)
        self.assertEqual(schema["properties"]["items"]["type"], "array")
        self.assertIn("title", schema["required"])
        self.assertEqual(
            schema["$defs"]["AIPlanItemSchema"]["properties"]["category"]["enum"],
            ["grocery", "daily_menu", "activity"],
        )

        def check_bounds(node):
            if isinstance(node, dict):
                self.assertFalse(
                    set(node)
                    & {"minLength", "maxLength", "minItems", "maxItems", "minimum", "maximum"}
                )
                for item in node.values():
                    check_bounds(item)
            elif isinstance(node, list):
                for item in node:
                    check_bounds(item)

        check_bounds(schema)
        for invalid in (
            {**valid, "items": []},
            {**valid, "items": valid["items"] * 201},
            {**valid, "items": [{**valid["items"][0], "price": -1}]},
            {**valid, "items": [{**valid["items"][0], "price": 2000000001}]},
            {**valid, "items": [{**valid["items"][0], "name": "x" * 256}]},
        ):
            with self.assertRaises(ValidationError):
                ai_service._parse_ai_response(
                    SimpleNamespace(parsed=None, text=json.dumps(invalid))
                )

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
        for code in (429, 403, 503, 504, None):
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
