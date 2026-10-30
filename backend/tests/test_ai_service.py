import json
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from app.main import app


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
TEST_API_KEY = "test-groq-key"


class AiProcessNotesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.payload = {
            "raw_notes": "Confidential test note: the team reviewed the launch schedule.",
            "participants": ["Alex"],
        }

    @staticmethod
    def _provider_client(response=None, side_effect=None):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.post = AsyncMock(return_value=response, side_effect=side_effect)
        return client

    @staticmethod
    def _provider_response(status_code: int, body: dict):
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = body
        response.request = httpx.Request("POST", GROQ_URL)
        return response

    def _post_with_provider(self, provider_client, model="openai/gpt-oss-20b"):
        environment = {"GROQ_API_KEY": TEST_API_KEY}
        if model is not None:
            environment["GROQ_MODEL"] = model
        with (
            patch.dict(os.environ, environment),
            patch("app.ai_service.httpx.AsyncClient", return_value=provider_client),
        ):
            return self.client.post("/api/ai/process-notes", json=self.payload)

    def test_process_notes_returns_analysis_using_groq_chat_completions(self) -> None:
        analysis = {
            "summary": "The team reviewed the launch schedule.",
            "decisions": [],
            "action_items": [],
            "blockers": [],
        }
        provider_client = self._provider_client(
            response=self._provider_response(
                200,
                {"choices": [{"message": {"content": json.dumps(analysis)}}]},
            )
        )

        response = self._post_with_provider(provider_client)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), analysis)
        request = provider_client.post.await_args
        self.assertEqual(request.args[0], GROQ_URL)
        self.assertEqual(request.kwargs["headers"]["Authorization"], f"Bearer {TEST_API_KEY}")
        self.assertEqual(request.kwargs["json"]["model"], "openai/gpt-oss-20b")
        self.assertEqual(request.kwargs["json"]["response_format"], {"type": "json_object"})
        self.assertEqual([message["role"] for message in request.kwargs["json"]["messages"]], ["system", "user"])
        self.assertIn(self.payload["raw_notes"], request.kwargs["json"]["messages"][1]["content"])

    def test_process_notes_uses_configured_groq_model(self) -> None:
        provider_client = self._provider_client(
            response=self._provider_response(
                200,
                {"choices": [{"message": {"content": '{"summary":"Reviewed."}'}}]},
            )
        )

        response = self._post_with_provider(provider_client, model="custom/model")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(provider_client.post.await_args.kwargs["json"]["model"], "custom/model")

    def test_process_notes_defaults_to_verified_groq_model(self) -> None:
        analysis = {"summary": "Reviewed."}
        provider_client = self._provider_client(
            response=self._provider_response(
                200,
                {"choices": [{"message": {"content": json.dumps(analysis)}}]},
            )
        )

        with (
            patch(
                "app.ai_service.os.getenv",
                side_effect=lambda name, default=None: (
                    TEST_API_KEY if name == "GROQ_API_KEY" else default
                ),
            ),
            patch("app.ai_service.httpx.AsyncClient", return_value=provider_client),
        ):
            response = self.client.post("/api/ai/process-notes", json=self.payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            provider_client.post.await_args.kwargs["json"]["model"],
            "openai/gpt-oss-20b",
        )

    def test_process_notes_reports_missing_groq_api_key(self) -> None:
        with (
            patch.dict(os.environ, {"GROQ_API_KEY": ""}),
            self.assertLogs("app.ai_service", level="ERROR") as captured,
        ):
            response = self.client.post("/api/ai/process-notes", json=self.payload)

        self.assertEqual(response.status_code, 503)
        self.assertIn("GROQ_API_KEY", response.json()["detail"])
        self.assertNotIn(TEST_API_KEY, "\n".join(captured.output))
        self.assertNotIn(self.payload["raw_notes"], "\n".join(captured.output))

    def test_process_notes_logs_provider_failures_without_sensitive_content(self) -> None:
        failures = (
            (
                401,
                {"error": {"message": "private provider detail", "code": "invalid_api_key"}},
                "authentication failed",
                "invalid_api_key",
            ),
            (
                429,
                {"error": {"message": "private provider detail", "code": "insufficient_quota"}},
                "quota is exhausted",
                "insufficient_quota",
            ),
            (
                429,
                {"error": {"message": "private provider detail", "code": "rate_limit_exceeded"}},
                "rate limit reached",
                "rate_limit_exceeded",
            ),
            (
                404,
                {"error": {"message": "private provider detail", "code": "model_not_found"}},
                "configured AI model is unavailable",
                "model_not_found",
            ),
        )
        for status, body, expected_message, expected_code in failures:
            with self.subTest(status=status, code=expected_code):
                provider_client = self._provider_client(
                    response=self._provider_response(status, body)
                )
                with self.assertLogs("app.ai_service", level="WARNING") as captured:
                    response = self._post_with_provider(provider_client)

                self.assertEqual(response.status_code, 502)
                self.assertIn(expected_message, response.json()["detail"])
                self.assertEqual(captured.records[0].provider_http_status, status)
                self.assertEqual(captured.records[0].provider_error_code, expected_code)
                self.assertNotIn("private provider detail", "\n".join(captured.output))
                self.assertNotIn(TEST_API_KEY, "\n".join(captured.output))
                self.assertNotIn(self.payload["raw_notes"], "\n".join(captured.output))

    def test_process_notes_reports_malformed_json_and_missing_fields(self) -> None:
        malformed_json_response = self._provider_response(200, {})
        malformed_json_response.json.side_effect = ValueError("invalid JSON")
        responses = (
            (self._provider_response(200, {}), "analysis content"),
            (malformed_json_response, "invalid"),
            (
                self._provider_response(
                    200,
                    {"choices": [{"message": {"content": "not valid json"}}]},
                ),
                "invalid",
            ),
            (
                self._provider_response(
                    200,
                    {"choices": [{"message": {"content": '{"decisions":[]}'}}]},
                ),
                "invalid",
            ),
        )

        for provider_response, expected_message in responses:
            with self.subTest(expected_message=expected_message):
                provider_client = self._provider_client(response=provider_response)
                with self.assertLogs("app.ai_service", level="ERROR") as captured:
                    response = self._post_with_provider(provider_client)
                self.assertEqual(response.status_code, 502)
                self.assertIn(expected_message, response.json()["detail"].lower())
                self.assertNotIn(self.payload["raw_notes"], "\n".join(captured.output))
                self.assertNotIn(TEST_API_KEY, "\n".join(captured.output))

    def test_process_notes_reports_provider_timeout(self) -> None:
        provider_client = self._provider_client(
            side_effect=httpx.ReadTimeout("private timeout detail")
        )

        with self.assertLogs("app.ai_service", level="WARNING") as captured:
            response = self._post_with_provider(provider_client)

        self.assertEqual(response.status_code, 504)
        self.assertIn("timed out", response.json()["detail"])
        self.assertNotIn("private timeout detail", "\n".join(captured.output))
        self.assertNotIn(TEST_API_KEY, "\n".join(captured.output))
        self.assertNotIn(self.payload["raw_notes"], "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
