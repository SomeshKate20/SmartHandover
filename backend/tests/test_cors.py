import unittest

from fastapi.testclient import TestClient

from app.main import app


DEPLOYED_ORIGINS = (
    "https://smart-handover-c6rb91ol3-someshs-projects-93b80e84.vercel.app",
    "https://smart-handover-dgder7wvt-someshs-projects-93b80e84.vercel.app",
)
UNRELATED_ORIGIN = "https://unrelated.example"


class CorsPreflightTests(unittest.TestCase):
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
