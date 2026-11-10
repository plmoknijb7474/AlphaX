import contextlib
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "render_sandbox_probe.py"
spec = importlib.util.spec_from_file_location("render_sandbox_probe_under_test", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FakeSandboxes:
    def __init__(self, cleanup_fails=False):
        self.root = tempfile.TemporaryDirectory(prefix="alpha-probe-test-")
        self.cleanup_fails = cleanup_fails
        self.terminated = []

    def create(self, **kwargs):
        self.create_kwargs = kwargs
        return types.SimpleNamespace(id="sandbox-test", region="oregon")

    def exec(self, sandbox_id, command):
        if "ALPHA_RENDER_COMMAND_OK" in command:
            yield types.SimpleNamespace(stream="stdout", data="ALPHA_RENDER_COMMAND_OK\n")
            yield types.SimpleNamespace(exit_code=0)
        elif "ALPHA_RENDER_PYTHON_OK" in command:
            yield types.SimpleNamespace(stream="stdout", data="Python 3.11\nALPHA_RENDER_PYTHON_OK\npip 24\n")
            yield types.SimpleNamespace(exit_code=0)
        elif "NETWORK_BLOCKED" in command:
            yield types.SimpleNamespace(stream="stdout", data="NETWORK_BLOCKED\n")
            yield types.SimpleNamespace(exit_code=0)
        else:
            yield types.SimpleNamespace(stream="stderr", data="unexpected command")
            yield types.SimpleNamespace(exit_code=1)

    def copy_to(self, sandbox_id, local_path, remote_path):
        dest = Path(self.root.name) / remote_path.lstrip("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest)

    def copy_from(self, sandbox_id, remote_path, local_path):
        src = Path(self.root.name) / remote_path.lstrip("/")
        shutil.copy2(src, local_path)

    def terminate(self, sandbox_id):
        self.terminated.append(sandbox_id)
        self.root.cleanup()
        if self.cleanup_fails:
            raise RuntimeError("simulated cleanup error")


class RenderSandboxProbeTests(unittest.TestCase):
    def _run_probe(self, cleanup_fails=False):
        sandboxes = FakeSandboxes(cleanup_fails=cleanup_fails)
        client = types.SimpleNamespace(sandboxes=sandboxes)
        fake_render = types.ModuleType("render")
        fake_render.Render = lambda **kwargs: client
        output = io.StringIO()
        env = {
            "RENDER_API_KEY": "test-key-not-real",
            "RENDER_WORKSPACE_ID": "workspace-test",
            "RENDER_SANDBOX_PLAN": "1c-2g",
        }
        with patch.dict(os.environ, env, clear=True), patch.dict(sys.modules, {"render": fake_render}), contextlib.redirect_stdout(output):
            result = mod.main()
        return result, output.getvalue(), sandboxes

    def test_probe_passes_all_checks_and_terminates_sandbox(self):
        result, output, sandboxes = self._run_probe()
        self.assertEqual(result, 0)
        self.assertIn("command_timeout_wrapper: PASS", output)
        self.assertIn("python_and_venv: PASS", output)
        self.assertIn("file_transfer: PASS", output)
        self.assertIn("network_denied: PASS", output)
        self.assertIn("sandbox_cleanup: PASS", output)
        self.assertEqual(sandboxes.terminated, ["sandbox-test"])
        self.assertEqual(sandboxes.create_kwargs["network_policy"], "deny-all")

    def test_cleanup_failure_makes_probe_fail(self):
        result, output, _sandboxes = self._run_probe(cleanup_fails=True)
        self.assertEqual(result, 1)
        self.assertIn("sandbox_cleanup: FAIL", output)


if __name__ == "__main__":
    unittest.main()
