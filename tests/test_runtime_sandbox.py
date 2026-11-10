import base64
import hashlib
import io
import os
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from runtime_sandbox import (
    RuntimeSandboxError,
    RuntimeSandboxManager,
    _SUPERVISOR,
    _safe_relative_path,
    _extract_zip_safely,
    SESSION_TTL_SECONDS,
)


class MemoryUpload:
    def __init__(self, filename, payload):
        self.filename = filename
        self._stream = io.BytesIO(payload)

    def read(self, size=-1):
        return self._stream.read(size)


def build_wheel():
    files = {
        "alpha_demo.py": b'VALUE = "local-wheel-installed"\n',
        "alpha_demo-1.0.0.dist-info/METADATA": (
            b"Metadata-Version: 2.1\nName: alpha-demo\nVersion: 1.0.0\n"
        ),
        "alpha_demo-1.0.0.dist-info/WHEEL": (
            b"Wheel-Version: 1.0\nGenerator: alpha-tests\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        ),
    }
    rows = []
    for path, content in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
        rows.append(f"{path},sha256={digest},{len(content)}")
    rows.append("alpha_demo-1.0.0.dist-info/RECORD,,")
    files["alpha_demo-1.0.0.dist-info/RECORD"] = ("\n".join(rows) + "\n").encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return output.getvalue()


def build_project_zip(include_wheel=False):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("main.py", 'print("ALPHA_RUNTIME_OK")\n')
        archive.writestr("README.md", "# Alpha runtime test\n")
        if include_wheel:
            archive.writestr("wheels/alpha_demo-1.0.0-py3-none-any.whl", build_wheel())
        archive.writestr(".env", "DO_NOT_IMPORT=secret\n")
    return output.getvalue()


class RuntimeSandboxUnitTests(unittest.TestCase):
    def test_runtime_is_disabled_by_default(self):
        with patch.dict(os.environ, {"ALPHA_SANDBOX_ENABLED": "0"}):
            status = RuntimeSandboxManager().capability_status()
        self.assertFalse(status["enabled"])
        self.assertFalse(status["ready"])
        self.assertIn("متوقف افتراضياً", status["note"])

    def test_supervisor_source_compiles_and_hides_control_process_memory(self):
        compile(_SUPERVISOR, "<alpha-runtime-supervisor>", "exec")
        self.assertIn("PR_SET_DUMPABLE = 0", _SUPERVISOR)
        self.assertIn("PR_SET_DUMPABLE failed", _SUPERVISOR)

    def test_safe_paths_reject_traversal_and_secrets(self):
        self.assertEqual(_safe_relative_path("src/main.py"), "src/main.py")
        self.assertIsNone(_safe_relative_path("../outside.py"))
        self.assertIsNone(_safe_relative_path("/etc/passwd"))
        self.assertIsNone(_safe_relative_path(".env"))
        self.assertIsNone(_safe_relative_path("private/key.pem"))

    def test_zip_extraction_skips_environment_files(self):
        raw = build_project_zip()
        with tempfile.TemporaryDirectory() as temp:
            count, total = _extract_zip_safely(raw, __import__("pathlib").Path(temp))
            self.assertEqual(count, 2)
            self.assertTrue(os.path.isfile(os.path.join(temp, "main.py")))
            self.assertFalse(os.path.exists(os.path.join(temp, ".env")))
            self.assertGreater(total, 0)

    def test_zip_extraction_rejects_parent_traversal(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("../escape.txt", "bad")
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(RuntimeSandboxError):
                _extract_zip_safely(output.getvalue(), __import__("pathlib").Path(temp))


class RuntimeSandboxIntegrationTests(unittest.TestCase):
    def _start_or_skip(self, manager, user_id, archive):
        status = manager.capability_status()
        if not status["available"]:
            self.skipTest("Host does not provide Linux namespace tools")
        try:
            return manager.start(user_id, [MemoryUpload("project.zip", archive)])
        except RuntimeSandboxError as exc:
            message = str(exc).lower()
            if "operation not permitted" in message or "namespace" in message or "العزل النظامي" in message:
                self.skipTest(f"Host restricts user namespaces/mounts: {exc}")
            raise

    def test_python_shell_network_ownership_venv_and_export(self):
        with patch.dict(os.environ, {"ALPHA_SANDBOX_ENABLED": "1"}):
            manager = RuntimeSandboxManager()
            started = self._start_or_skip(manager, "user-a", build_project_zip())
            sid = started["session_id"]
            try:
                py = manager.execute("user-a", sid, "python", path="main.py")["result"]
                self.assertTrue(py["ok"])
                self.assertIn("ALPHA_RUNTIME_OK", py["stdout"])

                shell = manager.execute("user-a", sid, "shell", command="pwd && python -V")["result"]
                self.assertTrue(shell["ok"])
                self.assertIn("/workspace", shell["stdout"])

                with patch.dict(os.environ, {"ALPHA_RUNTIME_HOST_SECRET": "must-not-enter-sandbox"}):
                    hidden = manager.execute(
                        "user-a", sid, "shell",
                        command='python -c "import os; print(os.getenv(\'ALPHA_RUNTIME_HOST_SECRET\', \'NOT_INHERITED\'))"',
                    )["result"]
                self.assertTrue(hidden["ok"])
                self.assertIn("NOT_INHERITED", hidden["stdout"])
                self.assertNotIn("must-not-enter-sandbox", hidden["stdout"])

                # A shell command may not leave background descendants running
                # after its foreground process has completed.
                background = manager.execute(
                    "user-a", sid, "shell",
                    command="python -c 'import time; f=open(\"bg-count.txt\",\"w\"); f.flush(); open(\"bg-ready.txt\",\"w\").close(); [(f.write(\"x\"), f.flush(), time.sleep(0.1)) for _ in range(30)]' & while [ ! -f bg-ready.txt ]; do sleep 0.01; done",
                )["result"]
                self.assertTrue(background["ok"])
                check_background = manager.execute(
                    "user-a", sid, "shell", command="sleep 0.5; wc -c bg-count.txt"
                )["result"]
                self.assertTrue(check_background["ok"])
                self.assertRegex(check_background["stdout"], r"\b(?:0|1) bg-count\.txt")

                network = manager.execute(
                    "user-a", sid, "shell",
                    command="python -c \"import socket; s=socket.socket(); s.settimeout(1); print(s.connect_ex(('1.1.1.1',53)))\"",
                )["result"]
                self.assertTrue(network["ok"])
                self.assertIn("101", network["stdout"])

                self.assertTrue(manager.execute("user-a", sid, "venv")["result"]["ok"])
                venv = manager.execute("user-a", sid, "shell", command="python -c \"import sys; print(sys.prefix)\"")["result"]
                self.assertIn("/workspace/.venv", venv["stdout"])

                with self.assertRaises(RuntimeSandboxError):
                    manager.status_for("user-b", sid)

                exported = manager.export("user-a", sid)
                with zipfile.ZipFile(io.BytesIO(exported)) as archive:
                    names = set(archive.namelist())
                self.assertIn("main.py", names)
                self.assertNotIn(".env", names)
                self.assertFalse(any(name.startswith(".venv/") for name in names))
            finally:
                manager.stop("user-a", sid)
            with self.assertRaises(RuntimeSandboxError):
                manager.status_for("user-a", sid)

    def test_idle_session_is_expired_and_cleaned(self):
        with patch.dict(os.environ, {"ALPHA_SANDBOX_ENABLED": "1"}):
            manager = RuntimeSandboxManager()
            started = self._start_or_skip(manager, "user-expiry", build_project_zip())
            sid = started["session_id"]
            process = manager._sessions[sid].process
            manager._sessions[sid].last_used -= SESSION_TTL_SECONDS + 1
            with self.assertRaises(RuntimeSandboxError):
                manager.status_for("user-expiry", sid)
            self.assertNotIn(sid, manager._sessions)
            self.assertIsNotNone(process.poll())
            manager.shutdown_all()

    def test_package_install_is_offline_and_uses_project_wheels(self):
        with patch.dict(os.environ, {"ALPHA_SANDBOX_ENABLED": "1"}):
            manager = RuntimeSandboxManager()
            started = self._start_or_skip(manager, "user-wheel", build_project_zip(include_wheel=True))
            sid = started["session_id"]
            try:
                self.assertTrue(manager.execute("user-wheel", sid, "venv")["result"]["ok"])
                installed = manager.execute("user-wheel", sid, "install", packages=["alpha-demo==1.0.0"])["result"]
                self.assertTrue(installed["ok"], installed)
                imported = manager.execute(
                    "user-wheel", sid, "shell",
                    command='python -c "import alpha_demo; print(alpha_demo.VALUE)"',
                )["result"]
                self.assertTrue(imported["ok"], imported)
                self.assertIn("local-wheel-installed", imported["stdout"])
                with self.assertRaises(RuntimeSandboxError):
                    manager.execute("user-wheel", sid, "install", packages=["https://example.invalid/pkg.whl"])
            finally:
                manager.stop("user-wheel", sid)


if __name__ == "__main__":
    unittest.main()
