import io
import os
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from runtime_sandbox import (
    RenderRuntimeSandboxManager,
    RuntimeSandboxError,
    RuntimeSandboxRouter,
)


class MemoryUpload:
    def __init__(self, filename, raw):
        self.filename = filename
        self.stream = io.BytesIO(raw)

    def read(self, size=-1):
        return self.stream.read(size)


def project_zip():
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("main.py", 'print("HELLO_RENDER")\n')
        archive.writestr("README.md", "# Remote sandbox fixture\n")
        archive.writestr(".env", "SECRET_SHOULD_NOT_BE_UPLOADED=1\n")
        archive.writestr(".venv/pyvenv.cfg", "home = /host\n")
    return result.getvalue()


class FakeSandboxes:
    def __init__(self):
        self.created = []
        self.terminated = []
        self.commands = []
        self.roots = {}

    def list_groups(self, limit=10):
        self.listed_limit = limit
        return SimpleNamespace(groups=[SimpleNamespace(id="group-test")])

    def create(self, **kwargs):
        self.created.append(kwargs)
        sandbox = SimpleNamespace(id="sbx-test", status="running", region="oregon")
        self.roots[sandbox.id] = tempfile.TemporaryDirectory(prefix="fake-render-sandbox-")
        return sandbox

    def exec(self, sandbox_id, command):
        self.commands.append((sandbox_id, command))
        yield SimpleNamespace(stream="stdout", data="REMOTE_EXEC_OK\n")
        yield SimpleNamespace(exit_code=0)

    def copy_to(self, sandbox_id, local_path, remote_path):
        root = Path(self.roots[sandbox_id].name)
        target = root / remote_path.lstrip("/")
        source = Path(local_path)
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            for child in source.iterdir():
                dst = target / child.name
                if child.is_dir():
                    import shutil
                    shutil.copytree(child, dst, dirs_exist_ok=True)
                else:
                    import shutil
                    shutil.copy2(child, dst)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(source, target)

    def copy_from(self, sandbox_id, remote_path, local_path):
        source = Path(self.roots[sandbox_id].name) / remote_path.lstrip("/")
        target = Path(local_path)
        import shutil
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            for child in source.iterdir():
                dst = target / child.name
                if child.is_dir():
                    shutil.copytree(child, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(child, dst)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def from_id(self, sandbox_id):
        return SimpleNamespace(id=sandbox_id, status="running")

    def terminate(self, sandbox_id):
        self.terminated.append(sandbox_id)
        holder = self.roots.pop(sandbox_id, None)
        if holder:
            holder.cleanup()


class FakeRenderClient:
    def __init__(self):
        self.sandboxes = FakeSandboxes()


class RenderSandboxAdapterTests(unittest.TestCase):
    def setUp(self):
        self.fake_client = FakeRenderClient()
        module = types.ModuleType("render")
        module.Render = lambda **kwargs: self.fake_client
        self.render_module_patch = patch.dict(sys.modules, {"render": module})
        self.render_module_patch.start()
        self.env_patch = patch.dict(os.environ, {
            "ALPHA_SANDBOX_ENABLED": "1",
            "ALPHA_RUNTIME_BACKEND": "render",
            "RENDER_API_KEY": "test-key-not-real",
            "RENDER_WORKSPACE_ID": "tea-test",
            "RENDER_SANDBOX_GROUP_ID": "group-test",
            "RENDER_SANDBOX_PLAN": "1c-2g",
        })
        self.env_patch.start()
        self.manager = RenderRuntimeSandboxManager()
        self.manager._make_client = lambda: self.fake_client

    def tearDown(self):
        self.manager.shutdown_all()
        self.env_patch.stop()
        self.render_module_patch.stop()

    def test_provider_probe_and_disabled_default(self):
        status = self.manager.capability_status()
        self.assertTrue(status["ready"])
        self.assertEqual(status["provider"], "render-sandboxes")
        self.assertEqual(status["network_policy"], "deny-all")
        self.assertEqual(status["region"], "oregon")
        self.assertEqual(self.fake_client.sandboxes.listed_limit, 100)
        self.assertIn("Oregon", status["data_region_notice"])
        with patch.dict(os.environ, {"ALPHA_SANDBOX_ENABLED": "0"}):
            disabled = self.manager.capability_status()
        self.assertFalse(disabled["ready"])

    def test_empty_workspace_can_use_render_auto_default_group(self):
        self.fake_client.sandboxes.list_groups = lambda limit=10: SimpleNamespace(groups=[])
        with patch.dict(os.environ, {"RENDER_SANDBOX_GROUP_ID": ""}):
            status = self.manager.capability_status()
        self.assertTrue(status["ready"])
        self.assertEqual(status["sandbox_group_count"], 0)

    def test_create_execute_export_ownership_and_stop(self):
        started = self.manager.start("user-1", [MemoryUpload("project.zip", project_zip())])
        sid = started["session_id"]
        self.assertEqual(started["file_count"], 2)
        self.assertEqual(self.fake_client.sandboxes.created[0]["network_policy"], "deny-all")
        self.assertEqual(self.fake_client.sandboxes.created[0]["sandbox_group_id"], "group-test")

        remote_tree = Path(self.fake_client.sandboxes.roots["sbx-test"].name) / "home/render/workspace"
        self.assertTrue((remote_tree / "main.py").is_file())
        self.assertFalse((remote_tree / ".env").exists())
        self.assertFalse((remote_tree / ".venv").exists())

        result = self.manager.execute("user-1", sid, "python", path="main.py")["result"]
        self.assertTrue(result["ok"])
        self.assertIn("REMOTE_EXEC_OK", result["stdout"])
        command = self.fake_client.sandboxes.commands[-1][1]
        self.assertIn("timeout", command)
        self.assertIn("/home/render/workspace", command)

        self.manager.execute("user-1", sid, "venv")
        self.manager.execute("user-1", sid, "install", packages=["pytest==8.0.0"])
        install_command = self.fake_client.sandboxes.commands[-1][1]
        self.assertIn("--no-index", install_command)
        self.assertIn("deny-all", self.manager.capability_status()["network_policy"])

        with self.assertRaises(RuntimeSandboxError):
            self.manager.status_for("user-2", sid)

        exported = self.manager.export("user-1", sid)
        with zipfile.ZipFile(io.BytesIO(exported)) as archive:
            names = set(archive.namelist())
        self.assertIn("main.py", names)
        self.assertNotIn(".env", names)
        self.assertFalse(any(name.startswith(".venv/") for name in names))

        self.assertTrue(self.manager.stop("user-1", sid))
        self.assertIn("sbx-test", self.fake_client.sandboxes.terminated)
        with self.assertRaises(RuntimeSandboxError):
            self.manager.status_for("user-1", sid)

    def test_invalid_shell_and_package_specs_are_rejected(self):
        started = self.manager.start("user-3", [MemoryUpload("project.zip", project_zip())])
        sid = started["session_id"]
        with self.assertRaises(RuntimeSandboxError):
            self.manager.execute("user-3", sid, "shell", command=" ")
        with self.assertRaises(RuntimeSandboxError):
            self.manager.execute("user-3", sid, "install", packages=["https://example.test/a.whl"])
        self.manager.stop("user-3", sid)

    def test_router_selects_render_backend(self):
        router = RuntimeSandboxRouter()
        self.assertIsInstance(router._backend, RenderRuntimeSandboxManager)
        router.shutdown_all()


if __name__ == "__main__":
    unittest.main()
