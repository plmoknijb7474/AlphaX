import os
import unittest
from unittest.mock import patch

try:
    import railway_runner
except ModuleNotFoundError as exc:
    if exc.name != "flask":
        raise
    railway_runner = None


@unittest.skipUnless(railway_runner is not None, "Flask is installed from requirements.txt in the Railway runner image")
class RailwayRunnerApiTests(unittest.TestCase):
    def setUp(self):
        self.client = railway_runner.app.test_client()
        self.env = patch.dict(os.environ, {"ALPHA_RUNNER_TOKEN": "runner-secret-" + "x" * 48})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.headers = {"Authorization": "Bearer " + os.environ["ALPHA_RUNNER_TOKEN"]}

    def test_health_is_liveness_only(self):
        response = self.client.get("/internal/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["service"], "alpha-runner")

    def test_internal_endpoints_require_shared_token(self):
        response = self.client.get("/internal/runtime/status")
        self.assertEqual(response.status_code, 401)

    def test_authorized_status_returns_runner_capabilities(self):
        with patch.object(railway_runner.manager, "capability_status", return_value={
            "enabled": True, "available": False, "ready": False, "missing": ["kernel"], "note": "not ready"
        }):
            response = self.client.get("/internal/runtime/status", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["runner"], "alpha-runner")
        self.assertFalse(response.get_json()["ready"])

    def test_invalid_user_identifier_is_rejected(self):
        response = self.client.post("/internal/runtime/start", headers=self.headers, data={"user_id": ""})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
