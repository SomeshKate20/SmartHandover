import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app, cors_origins


DEPLOYED_ORIGINS = (
    "https://smart-handover.vercel.app",
    "https://smart-handover-3a40vay71-someshs-projects-93b80e84.vercel.app",
    "https://smart-handover-c6rb91ol3-someshs-projects-93b80e84.vercel.app",
    "https://smart-handover-dgder7wvt-someshs-projects-93b80e84.vercel.app",
)
UNRELATED_ORIGIN = "https://unrelated.example"


class CorsPreflightTests(unittest.TestCase):
    def test_configured_origins_are_split_and_normalized(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CORS_ORIGINS": (
                    " https://custom.example/ , "
                    "https://another.example "
                ),
            },
        ):
            origins = cors_origins()

        self.assertIn("https://custom.example", origins)
        self.assertIn("https://another.example", origins)
        self.assertIn("http://localhost:5173", origins)

    def test_deployed_frontend_preflight_is_allowed_for_meetings_and_tasks(self) -> None:
        client = TestClient(app)
        for origin in DEPLOYED_ORIGINS:
            for path in ("/api/meetings", "/api/tasks"):
                with self.subTest(origin=origin, path=path):
                    response = client.options(
                        path,
                        headers={
                            "Origin": origin,
                            "Access-Control-Request-Method": "GET",
                            "Access-Control-Request-Headers": "content-type",
                        },
                    )

                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers["access-control-allow-origin"], origin)
                    allowed_methods = response.headers["access-control-allow-methods"]
                    for method in ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
                        self.assertIn(method, allowed_methods)
                    allowed_headers = response.headers["access-control-allow-headers"].lower()
                    self.assertIn("content-type", allowed_headers)
                    self.assertIn("authorization", allowed_headers)
                    self.assertNotIn("access-control-allow-credentials", response.headers)

    def test_unrelated_frontend_preflight_is_rejected(self) -> None:
        client = TestClient(app)
        for path in ("/api/meetings", "/api/tasks"):
            with self.subTest(path=path):
                response = client.options(
                    path,
                    headers={
                        "Origin": UNRELATED_ORIGIN,
                        "Access-Control-Request-Method": "GET",
                        "Access-Control-Request-Headers": "content-type",
                    },
                )

                self.assertEqual(response.status_code, 400)
                self.assertNotIn("access-control-allow-origin", response.headers)
