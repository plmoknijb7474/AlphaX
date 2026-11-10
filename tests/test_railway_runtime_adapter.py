import io
import os
import unittest
from unittest.mock import patch

from runtime_sandbox import RailwayRuntimeSandboxManager, RuntimeSandboxError, RuntimeSandboxRouter


class FakeResponse:
    def __init__(self, payload=None, status=200, content=b""):
        self._payload = payload or {}
        self.status_code = status
        self.content = content

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class RailwayRuntimeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "APP_ENV": "production",
            "ALPHA_SANDBOX_ENABLED": "1",
            "ALPHA_RUNNER_URL": "http://alpha-runner.railway.internal:8080",
            "ALPHA_RUNNER_TOKEN": "x" * 64,
            "ALPHA_RUNTIME_BACKEND": "railway",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.manager = RailwayRuntimeSandboxManager()

    def test_configuration_accepts_railway_private_url(self):
        _url, _token, missing = self.manager._configuration()
        self.assertEqual(missing, [])

    def test_configuration_rejects_public_runner_host(self):
        with patch.dict(os.environ, {"ALPHA_RUNNER_URL": "http://example.com:8080"}):
            _url, _token, missing = self.manager._configuration()
        self.assertTrue(any("Railway private networking" in item for item in missing))

    def test_status_probes_runner_and_reports_ready_only_when_runner_ready(self):
        self.manager._session = FakeSession([FakeResponse({
            "enabled": True, "available": True, "ready": True,
            "missing": [], "note": "runner ready", "runner": "alpha-runner",
        })])
        status = self.manager.capability_status()
        self.assertTrue(status["ready"])
        self.assertEqual(status["provider"], "railway-runner")
        self.assertEqual(self.manager._session.calls[0][2]["headers"]["Authorization"], "Bearer " + "x" * 64)

    def test_status_is_not_ready_when_runner_probe_fails(self):
        self.manager._session = FakeSession([FakeResponse({
            "enabled": True, "available": False, "ready": False,
            "missing": ["kernel namespace/mount/chroot permissions"],
            "note": "kernel blocked",
        })])
        status = self.manager.capability_status()
        self.assertFalse(status["ready"])
        self.assertIn("kernel blocked", status["note"])

    def test_start_strips_transport_ok_flag(self):
        self.manager._session = FakeSession([FakeResponse({"ok": True, "session_id": "sid", "file_count": 1})])
        upload = type("Upload", (), {"filename": "main.py", "mimetype": "text/x-python", "stream": io.BytesIO(b"print(1)")})()
        started = self.manager.start("user-1", [upload])
        self.assertEqual(started, {"session_id": "sid", "file_count": 1})

    def test_router_selects_railway_remote_adapter(self):
        router = RuntimeSandboxRouter()
        self.assertIsInstance(router._backend, RailwayRuntimeSandboxManager)

    def test_missing_token_fails_closed(self):
        with patch.dict(os.environ, {"ALPHA_RUNNER_TOKEN": "short"}):
            with self.assertRaises(RuntimeSandboxError):
                self.manager._request("GET", "/internal/runtime/status")


if __name__ == "__main__":
    unittest.main()
