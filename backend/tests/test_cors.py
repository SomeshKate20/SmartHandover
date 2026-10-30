import unittest

from fastapi.testclient import TestClient

from app.main import app


DEPLOYED_ORIGIN = "https://smart-handover-dgder7wvt-someshs-projects-93b80e84.vercel.app"


class CorsPreflightTests(unittest.TestCase):
    def test_deployed_frontend_preflight_is_allowed_for_meetings_and_tasks(self) -> None:
        client = TestClient(app)
        for path in ("/api/meetings", "/api/tasks"):
            with self.subTest(path=path):
                response = client.options(
                    path,
                    headers={
                        "Origin": DEPLOYED_ORIGIN,
                        "Access-Control-Request-Method": "GET",
                        "Access-Control-Request-Headers": "content-type",
                    },
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["access-control-allow-origin"], DEPLOYED_ORIGIN)
                self.assertIn("GET", response.headers["access-control-allow-methods"])
                self.assertIn("content-type", response.headers["access-control-allow-headers"].lower())
                self.assertNotIn("access-control-allow-credentials", response.headers)
