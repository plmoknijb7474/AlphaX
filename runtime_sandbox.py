"""Fail-closed Linux namespace sandbox for Alpha project runtime tools.

Project code is executed only inside a per-workspace user/mount/PID/network
namespace and chroot. No host environment variables, credentials, network, or
application source tree are mounted into the workspace. If the host cannot
create the required namespaces and mounts, execution is refused.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
import stat
import select
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

MAX_UPLOAD_FILES = 8
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_ARCHIVE_FILES = 500
MAX_SINGLE_FILE = 8 * 1024 * 1024
MAX_UNPACKED_BYTES = 24 * 1024 * 1024
MAX_EXPORT_BYTES = 18 * 1024 * 1024
MAX_COMMAND_CHARS = 6000
MAX_OUTPUT_CHARS = 180_000
SESSION_TTL_SECONDS = 20 * 60
MAX_SESSIONS = 2
MAX_SESSIONS_PER_USER = 1
MAX_SESSION_LIFETIME_SECONDS = 60 * 60
MAX_EXECUTIONS_PER_SESSION = 80

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", "coverage", ".next", ".nuxt", "vendor",
}
SECRET_DIRS = {".ssh", ".gnupg", ".aws", ".azure", ".config", "secrets", "credentials"}
SECRET_NAMES = {
    ".env", ".env.local", ".env.production", "id_rsa", "id_ed25519",
    "credentials.json", "service-account.json", "secrets.json", "token.json",
    ".netrc", ".npmrc", ".pypirc",
}
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".kdb", ".keystore"}
PACKAGE_SPEC_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}(?:==[A-Za-z0-9][A-Za-z0-9.+!-]{0,39})?$")


class RuntimeSandboxError(Exception):
    """A safe, user-displayable runtime error."""


@dataclass
class RuntimeSession:
    session_id: str
    user_id: str
    process: subprocess.Popen[str]
    tempdir: tempfile.TemporaryDirectory[str]
    created_at: float
    last_used: float
    lock: threading.RLock = field(default_factory=threading.RLock)
    logs: list[dict[str, Any]] = field(default_factory=list)
    execution_count: int = 0


# This supervisor is run inside unshare before chrooting. It owns the long-lived
# workspace and accepts JSON-line requests from the Flask process. Child jobs
# do not inherit its control pipes and /proc is intentionally not mounted.
_SUPERVISOR = r'''
import base64, ctypes, io, json, os, pathlib, re, resource, shutil, signal, subprocess, sys, tempfile, time, zipfile, stat

def emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()

def mount(args):
    result = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, text=True, timeout=8)
    if result.returncode != 0:
        raise RuntimeError("mount setup failed: " + (result.stderr or "").strip()[:300])

def safe_name(raw):
    if not isinstance(raw, str) or not raw or len(raw) > 220 or "\x00" in raw:
        return None
    name = raw.replace("\\", "/")
    p = pathlib.PurePosixPath(name)
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or any(x in ("", ".", "..") for x in p.parts):
        return None
    if any(part.lower() in {".git", ".hg", ".svn", "node_modules", ".ssh", ".aws", ".azure", "secrets", "credentials"} for part in p.parts[:-1]):
        return None
    base = p.name.lower()
    if base in {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519", "credentials.json", "service-account.json", "secrets.json", "token.json", ".netrc", ".npmrc", ".pypirc"}:
        return None
    if pathlib.PurePosixPath(base).suffix.lower() in {".pem", ".key", ".p12", ".pfx", ".kdb", ".keystore"}:
        return None
    if base.startswith(".env") and base not in {".env.example", ".env.sample", ".env.template"}:
        return None
    if any(part.lower() in {".venv", "venv", "env", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "build", "coverage", ".next", ".nuxt", "vendor"} for part in p.parts[:-1]):
        return None
    return p.as_posix()

def prepare(cfg):
    root = cfg["root"]
    mount([cfg["mount_bin"], "--make-rprivate", "/"])
    for source, target in cfg["readonly_mounts"]:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        os.makedirs(target, exist_ok=True)
        mount([cfg["mount_bin"], "--bind", source, target])
        mount([cfg["mount_bin"], "-o", "remount,bind,ro", target])
    for alias, target in cfg["aliases"].items():
        link = os.path.join(root, alias.lstrip("/"))
        os.makedirs(os.path.dirname(link), exist_ok=True)
        if os.path.lexists(link):
            if os.path.isdir(link) and not os.path.islink(link): shutil.rmtree(link)
            else: os.unlink(link)
        os.symlink(target, link)
    input_target = os.path.join(root, "input")
    os.makedirs(input_target, exist_ok=True)
    mount([cfg["mount_bin"], "--bind", cfg["input_dir"], input_target])
    mount([cfg["mount_bin"], "-o", "remount,bind,ro", input_target])
    workspace = os.path.join(root, "workspace")
    os.makedirs(workspace, exist_ok=True)
    mount([cfg["mount_bin"], "-t", "tmpfs", "-o", "size=128m,nosuid,nodev,mode=0755", "tmpfs", workspace])
    tmp = os.path.join(root, "tmp")
    os.makedirs(tmp, exist_ok=True)
    mount([cfg["mount_bin"], "-t", "tmpfs", "-o", "size=32m,nosuid,nodev,mode=1777", "tmpfs", tmp])
    dev = os.path.join(root, "dev")
    os.makedirs(dev, exist_ok=True)
    for node in ("null", "zero", "random", "urandom"):
        target = os.path.join(dev, node)
        open(target, "ab").close()
        mount([cfg["mount_bin"], "--bind", "/dev/" + node, target])
    etc = os.path.join(root, "etc")
    os.makedirs(etc, exist_ok=True)
    for filename, content in {
        "passwd": "root:x:0:0:root:/root:/bin/sh\nnobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin\n",
        "group": "root:x:0:\nnogroup:x:65534:\n",
        "hosts": "127.0.0.1 localhost\n::1 localhost\n",
        "nsswitch.conf": "passwd: files\ngroup: files\nhosts: files\n",
    }.items():
        Path = __import__("pathlib").Path
        Path(os.path.join(etc, filename)).write_text(content, encoding="utf-8")
    os.chroot(root)
    os.chdir("/workspace")
    shutil.copytree("/input", "/workspace", dirs_exist_ok=True, symlinks=False)
    # Restrict the visible tree before the first command.
    total = 0
    count = 0
    for base, dirs, files in os.walk("/workspace", followlinks=False):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(base, d))]
        for name in files:
            path = os.path.join(base, name)
            if os.path.islink(path):
                os.unlink(path); continue
            count += 1
            if count > 500: raise RuntimeError("project contains too many files")
            size = os.path.getsize(path); total += size
            if size > 8 * 1024 * 1024 or total > 24 * 1024 * 1024:
                raise RuntimeError("project exceeds sandbox upload limits")
    return count, total

def _limits():
    os.setsid()
    # A project process must not retain the namespace capabilities used by the
    # supervisor to mount the chroot. Fail closed if capability dropping fails.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise OSError(ctypes.get_errno(), "PR_SET_NO_NEW_PRIVS failed")
    class CapHeader(ctypes.Structure):
        _fields_ = [("version", ctypes.c_uint32), ("pid", ctypes.c_int)]
    class CapData(ctypes.Structure):
        _fields_ = [("effective", ctypes.c_uint32), ("permitted", ctypes.c_uint32), ("inheritable", ctypes.c_uint32)]
    header = CapHeader(0x20080522, 0)  # _LINUX_CAPABILITY_VERSION_3
    data = (CapData * 2)()
    if libc.capset(ctypes.byref(header), ctypes.byref(data)) != 0:
        raise OSError(ctypes.get_errno(), "capability drop failed")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (12, 14))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (24 * 1024 * 1024, 24 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_NPROC, (6, 6))
    resource.setrlimit(resource.RLIMIT_STACK, (8 * 1024 * 1024, 8 * 1024 * 1024))
    os.umask(0o077)

active_child = None

def _terminate_supervisor(signum, _frame):
    global active_child
    if active_child is not None and active_child.poll() is None:
        try: os.killpg(active_child.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        try: active_child.wait(timeout=2)
        except Exception: pass
    raise SystemExit(128 + signum)

signal.signal(signal.SIGTERM, _terminate_supervisor)
signal.signal(signal.SIGINT, _terminate_supervisor)

def run_child(req, python_exe):
    global active_child
    action = req.get("action")
    command_label = ""
    if action == "shell":
        command = req.get("command", "")
        if not isinstance(command, str) or not command.strip() or len(command) > 6000:
            raise ValueError("invalid shell command")
        argv = ["/bin/sh", "-c", command]
        command_label = command[:300]
    elif action == "python":
        rel = req.get("path", "")
        safe = safe_name(rel)
        if not safe or not safe.lower().endswith(".py"):
            raise ValueError("Python file path must be a safe relative .py path")
        target = os.path.realpath(os.path.join("/workspace", safe))
        if not target.startswith("/workspace/") or not os.path.isfile(target):
            raise ValueError("Python file was not found inside the project")
        venv_python = "/workspace/.venv/bin/python"
        argv = [venv_python if os.path.isfile(venv_python) else python_exe, "-I", "-B", target]
        command_label = "Python: " + safe
    elif action == "venv":
        argv = [python_exe, "-m", "venv", "--without-pip", ".venv"]
        command_label = "Create virtual environment: .venv"
    elif action == "install":
        packages = req.get("packages")
        if not os.path.isfile("/workspace/.venv/pyvenv.cfg"):
            raise ValueError("Create the .venv virtual environment before installing packages")
        wheel_dirs = ["/workspace/wheels", "/workspace/wheelhouse"]
        if not any(os.path.isdir(folder) and any(name.lower().endswith(".whl") for name in os.listdir(folder)) for folder in wheel_dirs):
            raise ValueError("No local wheel files found. Add .whl files under wheels/ or wheelhouse/ in the project ZIP")
        if not isinstance(packages, list) or not packages or len(packages) > 10:
            raise ValueError("select 1 to 10 package names")
        for item in packages:
            if not isinstance(item, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}(?:==[A-Za-z0-9][A-Za-z0-9.+!-]{0,39})?", item):
                raise ValueError("package names must use name or name==version; URLs and options are blocked")
        wheels = []
        for folder in ("/workspace/wheels", "/workspace/wheelhouse"):
            if os.path.isdir(folder): wheels.append("--find-links=" + folder)
        target_site = "/workspace/.venv/lib/python%d.%d/site-packages" % sys.version_info[:2]
        argv = [python_exe, "-m", "pip", "install", "--no-index", "--no-cache-dir", "--disable-pip-version-check", "--no-warn-script-location", "--target", target_site] + wheels + packages
        command_label = "Install offline packages: " + ", ".join(packages)
    else:
        raise ValueError("unknown runtime action")

    env = {
        "PATH": "/workspace/.venv/bin:/opt/pyvenv/bin:/usr/local/bin:/usr/bin:/bin",
        "HOME": "/workspace", "TMPDIR": "/tmp", "TMP": "/tmp", "TEMP": "/tmp",
        "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1",
        "PIP_NO_INDEX": "1", "PIP_FIND_LINKS": "/workspace/wheels /workspace/wheelhouse",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PIP_NO_CACHE_DIR": "1", "PIP_CONFIG_FILE": "/dev/null",
    }
    if os.path.isdir("/workspace/.venv"):
        env["VIRTUAL_ENV"] = "/workspace/.venv"
    start = time.monotonic()
    timed_out = False
    with tempfile.TemporaryFile(mode="w+b", dir="/tmp") as out, tempfile.TemporaryFile(mode="w+b", dir="/tmp") as err:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                cwd="/workspace", env=env, close_fds=True, preexec_fn=_limits)
        active_child = proc
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            timed_out = True
            try: os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            proc.wait(timeout=3)
        finally:
            # Kill background descendants even when the shell's foreground
            # process exits successfully (for example: `sleep 300 &`).
            try: os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            active_child = None
        out.seek(0); err.seek(0)
        stdout = out.read(90_001).decode("utf-8", "replace")
        stderr = err.read(90_001).decode("utf-8", "replace")
    duration = int((time.monotonic() - start) * 1000)
    return {
        "ok": proc.returncode == 0 and not timed_out,
        "action": action, "command": command_label, "exit_code": proc.returncode,
        "stdout": stdout[:90_000], "stderr": stderr[:90_000],
        "timed_out": timed_out, "duration_ms": duration,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

def export_project():
    excluded = {".git", "node_modules", ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", "build", "coverage", ".next", ".nuxt", "vendor"}
    buffer = io.BytesIO(); count = 0; total = 0
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=5) as archive:
        for base, dirs, files in os.walk("/workspace", followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in excluded and not os.path.islink(os.path.join(base, d)))
            for filename in sorted(files):
                path = os.path.join(base, filename)
                if os.path.islink(path): continue
                rel = os.path.relpath(path, "/workspace").replace(os.sep, "/")
                safe = safe_name(rel)
                if not safe: continue
                size = os.path.getsize(path)
                if size > 8 * 1024 * 1024: continue
                total += size; count += 1
                if count > 500 or total > 24 * 1024 * 1024: raise RuntimeError("workspace export exceeds limits")
                archive.write(path, safe)
    raw = buffer.getvalue()
    if len(raw) > 18 * 1024 * 1024: raise RuntimeError("workspace ZIP exceeds 18 MB")
    return {"ok": True, "archive_b64": base64.b64encode(raw).decode("ascii"), "file_count": count, "size_bytes": len(raw)}

def main():
    first = sys.stdin.readline()
    if not first: return 2
    cfg = json.loads(first)
    try:
        count, total = prepare(cfg)
        # The supervisor retains namespace capabilities and the control channel.
        # Hide its memory from same-UID workspace processes that have no such role.
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(4, 0, 0, 0, 0) != 0:  # PR_SET_DUMPABLE = 0
            raise OSError(ctypes.get_errno(), "PR_SET_DUMPABLE failed")
        emit({"ready": True, "file_count": count, "total_bytes": total})
    except Exception as exc:
        emit({"ready": False, "error": type(exc).__name__ + ": " + str(exc)[:350]})
        return 3
    python_exe = cfg["python_exe"]
    for line in sys.stdin:
        try:
            req = json.loads(line)
            op = req.get("action")
            if op == "export": result = export_project()
            elif op == "ping": result = {"ok": True, "pong": True}
            else: result = run_child(req, python_exe)
            emit(result)
        except Exception as exc:
            emit({"ok": False, "error": type(exc).__name__ + ": " + str(exc)[:500]})
    return 0

raise SystemExit(main())
'''


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_relative_path(raw: str) -> str | None:
    if not isinstance(raw, str) or not raw or len(raw) > 220 or "\x00" in raw:
        return None
    normalized = raw.replace("\\", "/")
    path = PurePosixPath(normalized)
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        return None
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    if any(part.lower() in SKIP_DIRS | SECRET_DIRS for part in path.parts[:-1]):
        return None
    base = path.name.lower()
    if base in SECRET_NAMES or (base.startswith(".env") and base not in {".env.example", ".env.sample", ".env.template"}):
        return None
    if path.suffix.lower() in SECRET_SUFFIXES:
        return None
    return path.as_posix()


def _extract_zip_safely(raw: bytes, destination: Path) -> tuple[int, int]:
    try:
        archive = zipfile.ZipFile(__import__("io").BytesIO(raw))
    except (zipfile.BadZipFile, OSError) as exc:
        raise RuntimeSandboxError("ملف ZIP غير صالح.") from exc
    count = 0
    total = 0
    seen: set[str] = set()
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ARCHIVE_FILES:
            raise RuntimeSandboxError("الأرشيف يحتوي عدداً كبيراً من الملفات.")
        for info in infos:
            if info.is_dir():
                continue
            path = _safe_relative_path(info.filename)
            if path is None:
                # Secret/build/dependency paths are intentionally skipped. Unsafe
                # traversal/absolute paths are rejected rather than normalized.
                raw_name = info.filename.replace("\\", "/")
                if raw_name.startswith("/") or re.match(r"^[A-Za-z]:", raw_name) or ".." in PurePosixPath(raw_name).parts:
                    raise RuntimeSandboxError("الأرشيف يحتوي على مسار خارج مجلد المشروع.")
                continue
            if path in seen:
                raise RuntimeSandboxError("الأرشيف يحتوي أسماء ملفات مكررة.")
            seen.add(path)
            if info.flag_bits & 0x1:
                raise RuntimeSandboxError("الأرشيف المشفّر غير مدعوم.")
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise RuntimeSandboxError("روابط الملفات الرمزية غير مسموحة داخل بيئة التنفيذ.")
            if info.file_size > MAX_SINGLE_FILE:
                raise RuntimeSandboxError("أحد ملفات المشروع يتجاوز 8 ميغابايت.")
            if info.file_size and (not info.compress_size or info.file_size / max(info.compress_size, 1) > 150):
                raise RuntimeSandboxError("نسبة ضغط أحد الملفات غير آمنة.")
            total += info.file_size
            if total > MAX_UNPACKED_BYTES:
                raise RuntimeSandboxError("الحجم الإجمالي بعد فك ZIP يتجاوز الحد الآمن البالغ 24 ميغابايت.")
            target = destination.joinpath(*PurePosixPath(path).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("xb") as output:
                remaining = MAX_SINGLE_FILE + 1
                while True:
                    chunk = source.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    output.write(chunk)
                    remaining -= len(chunk)
                    if remaining <= 0:
                        raise RuntimeSandboxError("ملف تجاوز الحد المسموح أثناء فك الضغط.")
            count += 1
    return count, total


def _build_input_from_uploads(files: list[Any], destination: Path) -> tuple[int, int]:
    if not files or len(files) > MAX_UPLOAD_FILES:
        raise RuntimeSandboxError("أرفق من 1 إلى 8 ملفات، بينها ZIP المشروع أو ملفات المصدر.")
    total_upload = 0
    count = 0
    total_content = 0
    zip_uploads = []
    other_uploads = []
    for upload in files:
        raw = upload.read(MAX_UPLOAD_BYTES + 1)
        total_upload += len(raw)
        if total_upload > MAX_UPLOAD_BYTES:
            raise RuntimeSandboxError("حجم الملفات المرفقة يتجاوز 20 ميغابايت.")
        filename = str(getattr(upload, "filename", "") or "")
        if filename.lower().endswith(".zip"):
            zip_uploads.append((filename, raw))
        else:
            other_uploads.append((filename, raw))
    if len(zip_uploads) > 1:
        raise RuntimeSandboxError("أرفق أرشيف ZIP واحداً فقط لكل مساحة تنفيذ.")
    if zip_uploads:
        count, total_content = _extract_zip_safely(zip_uploads[0][1], destination)
    for filename, raw in other_uploads:
        safe = _safe_relative_path(filename)
        if safe is None:
            raise RuntimeSandboxError("أحد أسماء الملفات المرفقة غير آمن أو حساس.")
        if len(raw) > MAX_SINGLE_FILE:
            raise RuntimeSandboxError("أحد الملفات يتجاوز 8 ميغابايت.")
        rel = f"wheels/{PurePosixPath(safe).name}" if safe.lower().endswith(".whl") else safe
        target = destination.joinpath(*PurePosixPath(rel).parts)
        if target.exists():
            raise RuntimeSandboxError("توجد ملفات مكررة بالاسم نفسه داخل المشروع.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        count += 1
        total_content += len(raw)
    if not count:
        raise RuntimeSandboxError("لم يتم العثور على ملفات مشروع قابلة للتشغيل.")
    if count > MAX_ARCHIVE_FILES or total_content > MAX_UNPACKED_BYTES:
        raise RuntimeSandboxError("محتوى المشروع يتجاوز حدود بيئة التنفيذ.")
    return count, total_content


def _mount_sources() -> tuple[list[tuple[str, str]], dict[str, str]]:
    readonly: list[tuple[str, str]] = []
    aliases: dict[str, str] = {}
    roots: list[str] = []
    for candidate in ("/usr", sys.prefix, sys.base_prefix, "/etc/ssl"):
        resolved = os.path.realpath(candidate)
        if os.path.isdir(resolved) and resolved not in roots:
            # /usr contains the interpreter's base libraries in this runtime.
            if any(resolved == item or resolved.startswith(item + os.sep) for item in roots):
                continue
            roots = [item for item in roots if not item.startswith(resolved + os.sep)]
            roots.append(resolved)
    for source in roots:
        readonly.append((source, source))
    for alias in ("/bin", "/sbin", "/lib", "/lib64"):
        path = Path(alias)
        if path.is_symlink():
            target = os.readlink(path)
            aliases[alias] = target
        elif path.is_dir() and os.path.realpath(alias) not in roots:
            source = os.path.realpath(alias)
            if source not in [x[0] for x in readonly]:
                readonly.append((source, alias))
    return readonly, aliases


def _create_root(root: Path) -> None:
    for rel in ("usr", "opt", "workspace", "input", "tmp", "dev", "etc"):
        (root / rel).mkdir(parents=True, exist_ok=True)
    for alias in ("bin", "sbin", "lib", "lib64"):
        target = root / alias
        if not target.exists() and not target.is_symlink():
            target.mkdir(parents=True, exist_ok=True)


def _read_protocol(process: subprocess.Popen[str], timeout: float) -> dict[str, Any]:
    if process.stdout is None:
        raise RuntimeSandboxError("قناة بيئة التنفيذ غير متاحة.")
    ready, _, _ = select.select([process.stdout], [], [], timeout)
    if not ready:
        raise RuntimeSandboxError("انتهت مهلة بدء بيئة التنفيذ المعزولة.")
    line = process.stdout.readline()
    if not line:
        error = ""
        if process.stderr:
            try:
                ready_err, _, _ = select.select([process.stderr], [], [], 0.1)
                if ready_err:
                    error = process.stderr.readline()[:300]
            except Exception:
                pass
        raise RuntimeSandboxError("تعذر بدء العزل النظامي." + (" " + error if error else ""))
    try:
        return json.loads(line)
    except json.JSONDecodeError as exc:
        raise RuntimeSandboxError("استجابة غير صالحة من بيئة التنفيذ.") from exc


class RuntimeSandboxManager:
    def __init__(self) -> None:
        self._sessions: dict[str, RuntimeSession] = {}
        self._starting_users: set[str] = set()
        self._lock = threading.RLock()
        self._unshare = shutil.which("unshare")
        self._mount = shutil.which("mount")
        self._probe_lock = threading.Lock()
        self._probe_checked_at = 0.0
        self._probe_result: tuple[bool, str] = (False, "لم يتم فحص العزل بعد")
        self._sweeper_stop = threading.Event()
        self._sweeper = threading.Thread(target=self._sweeper_loop, name="alpha-runtime-sweeper", daemon=True)
        self._sweeper.start()

    def _sweeper_loop(self) -> None:
        while not self._sweeper_stop.wait(30):
            try:
                self._cleanup_expired()
            except Exception:
                # Cleanup must never terminate the web worker's maintenance thread.
                continue

    def _probe_isolation(self) -> tuple[bool, str]:
        """Verify the exact namespace + tmpfs mount + chroot primitives, cached briefly."""
        now = time.monotonic()
        with self._probe_lock:
            if now - self._probe_checked_at < 45:
                return self._probe_result
            if not self._unshare or not self._mount:
                self._probe_result = (False, "أدوات unshare أو mount غير متوفرة")
                self._probe_checked_at = now
                return self._probe_result
            with tempfile.TemporaryDirectory(prefix="alpha-sandbox-probe-") as temp:
                root = Path(temp) / "root"
                (root / "tmp").mkdir(parents=True)
                probe = (
                    "import os,subprocess,sys;"
                    "root=sys.argv[1]; mount=sys.argv[2];"
                    "subprocess.run([mount,'--make-rprivate','/'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);"
                    "subprocess.run([mount,'-t','tmpfs','-o','size=1m,nosuid,nodev','tmpfs',root+'/tmp'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);"
                    "os.chroot(root); os.chdir('/'); assert os.path.isdir('/tmp')"
                )
                command = [self._unshare, "--user", "--map-root-user", "--mount", "--pid", "--fork", "--net", "--ipc", "--uts", sys.executable, "-I", "-c", probe, str(root), self._mount]
                env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "HOME": "/tmp", "TMPDIR": "/tmp"}
                try:
                    result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.PIPE, text=True, timeout=5, env=env,
                                            cwd="/", close_fds=True)
                    ok = result.returncode == 0
                    reason = "" if ok else (result.stderr or "فشل اختبار user namespace أو mount أو chroot")[:240]
                except (OSError, subprocess.TimeoutExpired) as exc:
                    ok, reason = False, str(exc)[:240]
            self._probe_result = (ok, reason)
            self._probe_checked_at = time.monotonic()
            return self._probe_result

    def capability_status(self) -> dict[str, Any]:
        enabled = os.environ.get("ALPHA_SANDBOX_ENABLED", "0").strip() == "1"
        missing = [name for name, value in (("unshare", self._unshare), ("mount", self._mount)) if not value]
        if not Path("/usr/sbin/chroot").exists() and not shutil.which("chroot"):
            missing.append("chroot")
        probe_reason = ""
        if enabled and not missing:
            supported, probe_reason = self._probe_isolation()
            if not supported:
                missing.append("kernel namespace/mount/chroot permissions")
        available = not missing
        return {
            "enabled": enabled,
            "available": available,
            "ready": enabled and available,
            "missing": missing,
            "isolation": "Linux user + mount + PID + network namespaces; chroot; no network; bounded tmpfs and process limits",
            "package_policy": "Offline wheel files only (place .whl files in wheels/ or wheelhouse/ inside the project ZIP).",
            "note": ("بيئة التنفيذ اجتازت اختبار العزل على هذا الخادم." if enabled and available else
                     "التنفيذ متوقف افتراضياً. يتطلب تفعيل ALPHA_SANDBOX_ENABLED=1 واجتياز اختبار user namespaces وmount وchroot على الخادم." if not enabled else
                     "الخادم لا يجتاز اختبار العزل المطلوب؛ لن يتم تنفيذ أي كود عليه."),
            "probe_detail": (probe_reason if enabled and not available else ""),
        }

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = []
        with self._lock:
            for sid, session in list(self._sessions.items()):
                if (now - session.last_used > SESSION_TTL_SECONDS
                        or now - session.created_at > MAX_SESSION_LIFETIME_SECONDS
                        or session.process.poll() is not None):
                    expired.append(sid)
            for sid in expired:
                self._stop_locked(sid)

    def _stop_locked(self, sid: str) -> None:
        item = self._sessions.pop(sid, None)
        if not item:
            return
        try:
            with item.lock:
                if item.process.stdin:
                    item.process.stdin.close()
                try:
                    os.killpg(item.process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                item.process.wait(timeout=2)
        except Exception:
            try:
                os.killpg(item.process.pid, signal.SIGKILL)
            except Exception:
                try: item.process.kill()
                except Exception: pass
            try: item.process.wait(timeout=2)
            except Exception: pass
        for stream in (item.process.stdin, item.process.stdout, item.process.stderr):
            try:
                if stream and not stream.closed: stream.close()
            except Exception:
                pass
        try: item.tempdir.cleanup()
        except Exception: pass

    def start(self, user_id: str | int, uploads: list[Any]) -> dict[str, Any]:
        self._cleanup_expired()
        status = self.capability_status()
        if not status["ready"]:
            raise RuntimeSandboxError(status["note"])
        uid = str(user_id)
        with self._lock:
            if uid in self._starting_users:
                raise RuntimeSandboxError("يتم تجهيز مساحة تنفيذ أخرى لهذا الحساب بالفعل.")
            owned = [sid for sid, item in self._sessions.items() if item.user_id == uid]
            if owned:
                for sid in owned:
                    self._stop_locked(sid)
            if len(self._sessions) + len(self._starting_users) >= MAX_SESSIONS:
                raise RuntimeSandboxError("بيئة التنفيذ مشغولة حالياً. أغلق جلسة أخرى أو أعد المحاولة لاحقاً.")
            self._starting_users.add(uid)

        holder: tempfile.TemporaryDirectory[str] | None = None
        process: subprocess.Popen[str] | None = None
        try:
            holder = tempfile.TemporaryDirectory(prefix="alpha-runtime-")
            base = Path(holder.name)
            root = base / "rootfs"
            input_dir = base / "input"
            input_dir.mkdir(mode=0o700)
            root.mkdir(mode=0o700)
            _create_root(root)
            count, total = _build_input_from_uploads(uploads, input_dir)
            readonly, aliases = _mount_sources()
            cfg = {
                "root": str(root), "input_dir": str(input_dir),
                "mount_bin": self._mount,
                "readonly_mounts": [(source, str(root / source.lstrip("/"))) for source, _target in readonly],
                "aliases": aliases, "python_exe": sys.executable,
            }
            helper = "import sys;\n" + _SUPERVISOR + "\n"
            cmd = [self._unshare, "--user", "--map-root-user", "--mount", "--pid", "--fork", "--net", "--ipc", "--uts",
                   sys.executable, "-I", "-c", helper]
            supervisor_env = {
                "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                "HOME": "/tmp", "TMPDIR": "/tmp",
            }
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, encoding="utf-8", errors="replace", bufsize=1,
                                       close_fds=True, cwd="/", env=supervisor_env, start_new_session=True)
            if process.stdin is None:
                raise RuntimeSandboxError("تعذر فتح قناة بدء بيئة التنفيذ.")
            process.stdin.write(json.dumps(cfg, separators=(",", ":")) + "\n")
            process.stdin.flush()
            ready = _read_protocol(process, 10)
            if not ready.get("ready"):
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait(timeout=2)
                raise RuntimeSandboxError("فشل إعداد العزل: " + str(ready.get("error", "unknown error"))[:350])
            sid = str(uuid.uuid4())
            item = RuntimeSession(sid, uid, process, holder, time.time(), time.time())
            with self._lock:
                self._sessions[sid] = item
            return {"session_id": sid, "file_count": ready.get("file_count", count),
                    "size_bytes": ready.get("total_bytes", total), "expires_in_seconds": SESSION_TTL_SECONDS}
        except Exception:
            if process is not None:
                if process.poll() is None:
                    try: os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    try: process.wait(timeout=2)
                    except Exception: pass
                for stream in (process.stdin, process.stdout, process.stderr):
                    try:
                        if stream and not stream.closed: stream.close()
                    except Exception:
                        pass
            if holder is not None:
                try: holder.cleanup()
                except Exception: pass
            raise
        finally:
            with self._lock:
                self._starting_users.discard(uid)

    def _get_owned(self, user_id: str | int, session_id: str) -> RuntimeSession:
        try:
            sid = str(uuid.UUID(str(session_id)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise RuntimeSandboxError("معرّف جلسة التنفيذ غير صالح.") from exc
        with self._lock:
            item = self._sessions.get(sid)
            if item is None or item.user_id != str(user_id):
                raise RuntimeSandboxError("جلسة التنفيذ غير موجودة أو انتهت. ابدأ جلسة جديدة وأرفق المشروع مجدداً.")
            now = time.time()
            if (now - item.last_used > SESSION_TTL_SECONDS
                    or now - item.created_at > MAX_SESSION_LIFETIME_SECONDS):
                self._stop_locked(sid)
                raise RuntimeSandboxError("انتهت مدة جلسة التنفيذ. ابدأ جلسة جديدة وأرفق المشروع مجدداً.")
            if item.process.poll() is not None:
                self._stop_locked(sid)
                raise RuntimeSandboxError("توقفت بيئة التنفيذ. ابدأ جلسة جديدة وأرفق المشروع مجدداً.")
            item.last_used = now
            return item

    def _request(self, item: RuntimeSession, payload: dict[str, Any], timeout: float = 30) -> dict[str, Any]:
        with item.lock:
            if item.process.poll() is not None or item.process.stdin is None:
                raise RuntimeSandboxError("انتهت جلسة التنفيذ. أنشئ جلسة جديدة.")
            try:
                item.process.stdin.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
                item.process.stdin.flush()
                result = _read_protocol(item.process, timeout)
            except (BrokenPipeError, OSError, RuntimeSandboxError):
                # Do not acquire the manager lock while holding item.lock: the
                # expiry sweeper takes those locks in the opposite order.
                # The sweeper or the next ownership check will reap dead sessions.
                raise
            item.last_used = time.time()
            return result

    def execute(self, user_id: str | int, session_id: str, action: str, *, command: str = "", path: str = "", packages: list[str] | None = None) -> dict[str, Any]:
        item = self._get_owned(user_id, session_id)
        if action not in {"shell", "python", "venv", "install"}:
            raise RuntimeSandboxError("نوع العملية غير مدعوم.")
        if action == "shell" and (not isinstance(command, str) or not command.strip() or len(command) > MAX_COMMAND_CHARS):
            raise RuntimeSandboxError("اكتب أمراً من 1 إلى 6000 حرف.")
        if action == "python":
            safe = _safe_relative_path(path)
            if not safe or not safe.lower().endswith(".py"):
                raise RuntimeSandboxError("حدد مسار ملف Python نسبيّاً مثل main.py.")
            path = safe
        if action == "install":
            if not isinstance(packages, list) or not 1 <= len(packages) <= 10 or any(not isinstance(x, str) or not PACKAGE_SPEC_RE.fullmatch(x) for x in packages):
                raise RuntimeSandboxError("أدخل من 1 إلى 10 أسماء حزم بصيغة package أو package==version فقط؛ الروابط والأوامر غير مسموحة.")
        with item.lock:
            if item.execution_count >= MAX_EXECUTIONS_PER_SESSION:
                raise RuntimeSandboxError("تم بلوغ الحد الأقصى لعدد العمليات في الجلسة. أوقفها وابدأ جلسة جديدة.")
            result = self._request(item, {"action": action, "command": command, "path": path, "packages": packages or []})
            if result.get("error"):
                raise RuntimeSandboxError(str(result["error"])[:500])
            item.execution_count += 1
        safe_result = {
            "ok": bool(result.get("ok")), "action": action,
            "command": str(result.get("command", ""))[:400],
            "exit_code": result.get("exit_code"), "stdout": str(result.get("stdout", ""))[:MAX_OUTPUT_CHARS],
            "stderr": str(result.get("stderr", ""))[:MAX_OUTPUT_CHARS],
            "timed_out": bool(result.get("timed_out")), "duration_ms": int(result.get("duration_ms", 0)),
            "created_at": str(result.get("created_at") or _utc_now()),
        }
        item.logs.append(safe_result)
        item.logs[:] = item.logs[-40:]
        return {"result": safe_result, "logs": item.logs[-20:], "session_id": item.session_id,
                "expires_in_seconds": SESSION_TTL_SECONDS}

    def export(self, user_id: str | int, session_id: str) -> bytes:
        item = self._get_owned(user_id, session_id)
        result = self._request(item, {"action": "export"}, timeout=20)
        if not result.get("ok") or not isinstance(result.get("archive_b64"), str):
            raise RuntimeSandboxError(str(result.get("error", "تعذر تصدير مساحة المشروع."))[:400])
        try:
            raw = base64.b64decode(result["archive_b64"], validate=True)
        except (ValueError, TypeError) as exc:
            raise RuntimeSandboxError("تعذر فك نسخة المشروع المصدّرة.") from exc
        if len(raw) > MAX_EXPORT_BYTES:
            raise RuntimeSandboxError("نسخة المشروع أكبر من الحد المسموح للتنزيل.")
        return raw

    def stop(self, user_id: str | int, session_id: str) -> bool:
        item = self._get_owned(user_id, session_id)
        with self._lock:
            self._stop_locked(item.session_id)
        return True

    def status_for(self, user_id: str | int, session_id: str) -> dict[str, Any]:
        item = self._get_owned(user_id, session_id)
        return {"active": True, "session_id": item.session_id, "logs": item.logs[-20:],
                "expires_in_seconds": max(0, SESSION_TTL_SECONDS - int(time.time() - item.last_used))}

    def shutdown_all(self) -> None:
        self._sweeper_stop.set()
        with self._lock:
            for sid in list(self._sessions):
                self._stop_locked(sid)




@dataclass
class RenderRuntimeSession:
    """A user-owned session backed by a managed Render Sandbox."""
    session_id: str
    user_id: str
    sandbox_id: str
    created_at: float
    last_used: float
    lock: threading.RLock = field(default_factory=threading.RLock)
    logs: list[dict[str, Any]] = field(default_factory=list)
    execution_count: int = 0


class RenderRuntimeSandboxManager:
    """Managed Render Sandboxes adapter. Project code never runs in the Flask worker."""

    REMOTE_ROOT = "/home/render/workspace"
    COMMAND_TIMEOUT_SECONDS = 20
    SANDBOX_RUNTIME_SECONDS = 3600
    SANDBOX_IDLE_SECONDS = 1200

    def __init__(self) -> None:
        self._sessions: dict[str, RenderRuntimeSession] = {}
        self._starting_users: set[str] = set()
        self._lock = threading.RLock()
        self._probe_lock = threading.Lock()
        self._probe_checked_at = 0.0
        self._probe_result: tuple[bool, str, int] = (False, "لم يتم الاتصال بخدمة Render Sandboxes بعد", 0)
        self._client_instance = None
        self._sweeper_stop = threading.Event()
        self._sweeper = threading.Thread(
            target=self._sweeper_loop, name="alpha-render-sandbox-sweeper", daemon=True
        )
        self._sweeper.start()

    @staticmethod
    def _enabled() -> bool:
        return os.environ.get("ALPHA_SANDBOX_ENABLED", "0").strip() == "1"

    @staticmethod
    def _configured() -> tuple[bool, list[str]]:
        missing = []
        if not os.environ.get("RENDER_API_KEY", "").strip():
            missing.append("RENDER_API_KEY")
        if not os.environ.get("RENDER_WORKSPACE_ID", "").strip():
            missing.append("RENDER_WORKSPACE_ID")
        try:
            import render  # noqa: F401
        except Exception:
            missing.append("Render Python SDK (render>=1.8.0)")
        return not missing, missing

    def _make_client(self):
        if self._client_instance is not None:
            return self._client_instance
        try:
            from render import Render
            token = os.environ.get("RENDER_API_KEY", "").strip()
            owner_id = os.environ.get("RENDER_WORKSPACE_ID", "").strip()
            self._client_instance = Render(token=token, owner_id=owner_id)
            return self._client_instance
        except Exception as exc:
            raise RuntimeSandboxError(
                "تعذر تحميل عميل Render Sandboxes. تحقق من تثبيت render>=1.8.0 وإعداد مفاتيح الخدمة."
            ) from exc

    def _probe_provider(self, force: bool = False) -> tuple[bool, str, int]:
        now = time.monotonic()
        with self._probe_lock:
            if not force and now - self._probe_checked_at < 60:
                return self._probe_result
            configured, missing = self._configured()
            if not configured:
                result = (False, "إعداد Render Sandboxes ناقص: " + ", ".join(missing), 0)
            else:
                try:
                    client = self._make_client()
                    groups = client.sandboxes.list_groups(limit=100)
                    group_items = getattr(groups, "groups", None)
                    if group_items is None and isinstance(groups, dict):
                        group_items = groups.get("groups", [])
                    group_items = group_items or []
                    configured_group = os.environ.get("RENDER_SANDBOX_GROUP_ID", "").strip()
                    if configured_group and not any(str(getattr(x, "id", x.get("id") if isinstance(x, dict) else "")) == configured_group for x in group_items):
                        result = (False, "معرّف RENDER_SANDBOX_GROUP_ID غير موجود ضمن مجموعات مساحة العمل.", len(group_items))
                    elif not group_items and not configured_group:
                        # Render creates the workspace's first default group automatically
                        # when the first sandbox is created. Do not create resources in GET status.
                        result = (True, "تم التحقق من Render API. لا توجد Sandbox Group بعد؛ سيُنشئ Render المجموعة الافتراضية عند أول إنشاء Sandbox.", 0)
                    else:
                        result = (True, "تم الاتصال بواجهة Render Sandboxes والتحقق من مجموعة التنفيذ. لم يتم إنشاء Sandbox في فحص الحالة.", len(group_items))
                except Exception as exc:
                    # SDK errors may contain request details; never return them to the browser.
                    result = (False, "تعذر الاتصال بواجهة Render Sandboxes (" + type(exc).__name__ + ").", 0)
            self._probe_result = result
            self._probe_checked_at = time.monotonic()
            return result

    def capability_status(self) -> dict[str, Any]:
        enabled = self._enabled()
        configured, missing = self._configured()
        connected, detail, group_count = self._probe_provider() if configured and enabled else (False, "", 0)
        if not configured:
            note = "خدمة Render Sandboxes غير مكتملة الإعداد. أضف SDK ومفتاح API ومعرّف مساحة العمل في متغيرات Render."
        elif not enabled:
            note = "موصل Render Sandboxes جاهز للإعداد لكنه متوقف افتراضياً. راجع نقل ملفات المشاريع إلى منطقة Oregon قبل تفعيل التنفيذ."
        elif connected:
            note = "اتصال Render Sandboxes ناجح. سيتم تنفيذ المشروع داخل Sandbox مستقل بسياسة شبكة deny-all."
        else:
            note = detail or "تعذر التحقق من خدمة Render Sandboxes."
        return {
            "provider": "render-sandboxes",
            "enabled": enabled,
            "available": configured and connected,
            "ready": enabled and configured and connected,
            "missing": missing,
            "sandbox_group_count": group_count,
            "region": "oregon",
            "network_policy": "deny-all",
            "isolation": "Managed Render Sandbox; project files are transferred to a separate ephemeral sandbox. No outbound network access.",
            "package_policy": "Offline wheel files only under wheels/ or wheelhouse/.",
            "note": note,
            "probe_detail": detail if enabled and not connected else "",
            "beta": True,
            "data_region_notice": "تُرسل ملفات المشروع إلى بيئة Render Sandboxes في Oregon؛ لا ترفع ملفات حساسة قبل قبول هذا النقل.",
        }

    def _sweeper_loop(self) -> None:
        while not self._sweeper_stop.wait(30):
            try:
                self._cleanup_expired()
            except Exception:
                continue

    def _terminate_remote(self, sandbox_id: str) -> None:
        try:
            self._make_client().sandboxes.terminate(sandbox_id)
        except Exception:
            # Remote TTL also guarantees eventual cleanup if the API is temporarily unavailable.
            pass

    def _stop_locked(self, sid: str) -> None:
        item = self._sessions.pop(sid, None)
        if item:
            with item.lock:
                self._terminate_remote(item.sandbox_id)

    def _cleanup_expired(self) -> None:
        now = time.time()
        with self._lock:
            expired = [
                sid for sid, item in self._sessions.items()
                if now - item.last_used > SESSION_TTL_SECONDS
                or now - item.created_at > MAX_SESSION_LIFETIME_SECONDS
            ]
            for sid in expired:
                self._stop_locked(sid)

    def start(self, user_id: str | int, uploads: list[Any]) -> dict[str, Any]:
        self._cleanup_expired()
        status = self.capability_status()
        if not status["ready"]:
            raise RuntimeSandboxError(status["note"])
        uid = str(user_id)
        with self._lock:
            if uid in self._starting_users:
                raise RuntimeSandboxError("يتم تجهيز مساحة تنفيذ أخرى لهذا الحساب بالفعل.")
            owned = [sid for sid, item in self._sessions.items() if item.user_id == uid]
            for sid in owned:
                self._stop_locked(sid)
            if len(self._sessions) + len(self._starting_users) >= MAX_SESSIONS:
                raise RuntimeSandboxError("بيئة التنفيذ مشغولة حالياً. أغلق جلسة أخرى أو أعد المحاولة لاحقاً.")
            self._starting_users.add(uid)

        holder = None
        sandbox = None
        try:
            holder = tempfile.TemporaryDirectory(prefix="alpha-render-upload-")
            input_dir = Path(holder.name) / "workspace"
            input_dir.mkdir(mode=0o700)
            count, total = _build_input_from_uploads(uploads, input_dir)
            client = self._make_client()
            create_kwargs = {
                "plan": os.environ.get("RENDER_SANDBOX_PLAN", "1c-2g").strip(),
                "timeout_seconds": self.SANDBOX_RUNTIME_SECONDS,
                "idle_timeout_seconds": self.SANDBOX_IDLE_SECONDS,
                "network_policy": "deny-all",
                "wait": True,
            }
            if os.environ.get("RENDER_SANDBOX_GROUP_ID", "").strip():
                create_kwargs["sandbox_group_id"] = os.environ["RENDER_SANDBOX_GROUP_ID"].strip()
            sandbox = client.sandboxes.create(**create_kwargs)
            mkdir_exit = None
            for event in client.sandboxes.exec(sandbox.id, "mkdir -p " + shlex.quote(self.REMOTE_ROOT)):
                if isinstance(event, dict) and "exit_code" in event:
                    mkdir_exit = int(event["exit_code"])
                elif hasattr(event, "exit_code"):
                    mkdir_exit = int(event.exit_code)
            if mkdir_exit != 0:
                raise RuntimeSandboxError("تعذر تجهيز مجلد المشروع داخل Render Sandbox.")
            client.sandboxes.copy_to(sandbox.id, str(input_dir), self.REMOTE_ROOT)
            sid = str(uuid.uuid4())
            item = RenderRuntimeSession(sid, uid, sandbox.id, time.time(), time.time())
            with self._lock:
                self._sessions[sid] = item
            return {
                "session_id": sid, "file_count": count, "size_bytes": total,
                "expires_in_seconds": SESSION_TTL_SECONDS,
                "provider": "render-sandboxes", "region": "oregon",
            }
        except RuntimeSandboxError:
            if sandbox is not None:
                self._terminate_remote(sandbox.id)
            raise
        except Exception as exc:
            if sandbox is not None:
                self._terminate_remote(sandbox.id)
            raise RuntimeSandboxError(
                "تعذر تجهيز Sandbox على Render (" + type(exc).__name__ + "). تحقق من صلاحيات الحساب ومجموعة Sandbox والحدود المتاحة."
            ) from exc
        finally:
            if holder is not None:
                holder.cleanup()
            with self._lock:
                self._starting_users.discard(uid)

    def _get_owned(self, user_id: str | int, session_id: str) -> RenderRuntimeSession:
        try:
            sid = str(uuid.UUID(str(session_id)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise RuntimeSandboxError("معرّف جلسة التنفيذ غير صالح.") from exc
        with self._lock:
            item = self._sessions.get(sid)
            if item is None or item.user_id != str(user_id):
                raise RuntimeSandboxError("جلسة التنفيذ غير موجودة أو انتهت. ابدأ جلسة جديدة وأرفق المشروع مجدداً.")
            now = time.time()
            if now - item.last_used > SESSION_TTL_SECONDS or now - item.created_at > MAX_SESSION_LIFETIME_SECONDS:
                self._stop_locked(sid)
                raise RuntimeSandboxError("انتهت مدة جلسة التنفيذ. ابدأ جلسة جديدة وأرفق المشروع مجدداً.")
            item.last_used = now
            return item

    def _run_remote(self, item: RenderRuntimeSession, shell_command: str) -> dict[str, Any]:
        client = self._make_client()
        wrapped = (
            "cd " + shlex.quote(self.REMOTE_ROOT) + " && "
            "timeout --signal=TERM --kill-after=2s " + str(self.COMMAND_TIMEOUT_SECONDS) + "s "
            "bash -c " + shlex.quote(shell_command)
        )
        started = time.monotonic()
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        total_chars = 0
        exit_code = None
        try:
            for event in client.sandboxes.exec(item.sandbox_id, wrapped):
                if isinstance(event, dict) and "exit_code" in event:
                    exit_code = int(event["exit_code"])
                    continue
                if hasattr(event, "exit_code"):
                    exit_code = int(event.exit_code)
                    continue
                if isinstance(event, dict):
                    stream = event.get("stream")
                    data = event.get("data", "")
                else:
                    stream = getattr(event, "stream", None)
                    data = getattr(event, "data", "")
                chunk = str(data or "")
                total_chars += len(chunk)
                if total_chars > MAX_OUTPUT_CHARS:
                    self._stop_locked(item.session_id)
                    raise RuntimeSandboxError("تجاوز خرج الأمر الحد الآمن؛ تم إنهاء Sandbox لحماية الخدمة.")
                (stderr_parts if stream == "stderr" else stdout_parts).append(chunk)
            if exit_code is None:
                raise RuntimeSandboxError("انقطع تدفق نتائج الأمر قبل استلام رمز الخروج.")
        except RuntimeSandboxError:
            raise
        except Exception as exc:
            raise RuntimeSandboxError("تعذر تنفيذ الأمر داخل Render Sandbox (" + type(exc).__name__ + ").") from exc
        duration = int((time.monotonic() - started) * 1000)
        return {
            "exit_code": exit_code,
            "stdout": "".join(stdout_parts),
            "stderr": "".join(stderr_parts),
            "duration_ms": duration,
            "timed_out": exit_code == 124 or exit_code == 137,
            "created_at": _utc_now(),
        }

    def execute(
        self, user_id: str | int, session_id: str, action: str, *,
        command: str = "", path: str = "", packages: list[str] | None = None,
    ) -> dict[str, Any]:
        item = self._get_owned(user_id, session_id)
        if action not in {"shell", "python", "venv", "install"}:
            raise RuntimeSandboxError("نوع العملية غير مدعوم.")
        if action == "shell":
            if not isinstance(command, str) or not command.strip() or len(command) > MAX_COMMAND_CHARS:
                raise RuntimeSandboxError("اكتب أمراً من 1 إلى 6000 حرف.")
            shell_command, label = command, command[:300]
        elif action == "python":
            safe = _safe_relative_path(path)
            if not safe or not safe.lower().endswith(".py"):
                raise RuntimeSandboxError("حدد مسار ملف Python نسبيّاً مثل main.py.")
            shell_command = "test -f " + shlex.quote(safe) + " && python3 -B " + shlex.quote(safe)
            label = "Python: " + safe
        elif action == "venv":
            shell_command = "python3 -m venv .venv"
            label = "Create virtual environment: .venv"
        else:
            if not isinstance(packages, list) or not 1 <= len(packages) <= 10 or any(
                not isinstance(x, str) or not PACKAGE_SPEC_RE.fullmatch(x) for x in packages
            ):
                raise RuntimeSandboxError("أدخل من 1 إلى 10 أسماء حزم بصيغة package أو package==version فقط.")
            shell_command = (
                "test -d .venv || { echo 'Create .venv first'; exit 2; }; "
                "find wheels wheelhouse -maxdepth 1 -type f -name '*.whl' -print -quit 2>/dev/null | grep -q . "
                "|| { echo 'No local wheel files found in wheels/ or wheelhouse/'; exit 2; }; "
                "./.venv/bin/python -m pip install --no-index --no-cache-dir --disable-pip-version-check "
                "--find-links=./wheels --find-links=./wheelhouse " + shlex.join(packages)
            )
            label = "Install offline packages: " + ", ".join(packages)

        with item.lock:
            if item.execution_count >= MAX_EXECUTIONS_PER_SESSION:
                raise RuntimeSandboxError("تم بلوغ الحد الأقصى لعدد العمليات في الجلسة. أوقفها وابدأ جلسة جديدة.")
            result = self._run_remote(item, shell_command)
            item.execution_count += 1
            safe_result = {
                "ok": result["exit_code"] == 0 and not result["timed_out"],
                "action": action, "command": label, "exit_code": result["exit_code"],
                "stdout": result["stdout"][:MAX_OUTPUT_CHARS],
                "stderr": result["stderr"][:MAX_OUTPUT_CHARS],
                "timed_out": result["timed_out"], "duration_ms": result["duration_ms"],
                "created_at": result["created_at"],
            }
            item.logs.append(safe_result)
            item.logs[:] = item.logs[-40:]
            item.last_used = time.time()
        return {
            "result": safe_result, "logs": item.logs[-20:], "session_id": item.session_id,
            "expires_in_seconds": SESSION_TTL_SECONDS,
        }

    def export(self, user_id: str | int, session_id: str) -> bytes:
        item = self._get_owned(user_id, session_id)
        client = self._make_client()
        with tempfile.TemporaryDirectory(prefix="alpha-render-export-") as temp:
            destination = Path(temp) / "workspace"
            destination.mkdir()
            try:
                client.sandboxes.copy_from(item.sandbox_id, self.REMOTE_ROOT, str(destination))
            except Exception as exc:
                raise RuntimeSandboxError("تعذر تنزيل ملفات المشروع من Render Sandbox (" + type(exc).__name__ + ").") from exc
            buffer = __import__("io").BytesIO()
            count = total = 0
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=5) as archive:
                for base, dirs, files in os.walk(destination, followlinks=False):
                    dirs[:] = sorted(
                        d for d in dirs
                        if d.lower() not in SKIP_DIRS | SECRET_DIRS
                        and not os.path.islink(os.path.join(base, d))
                    )
                    for filename in sorted(files):
                        absolute = Path(base) / filename
                        if absolute.is_symlink() or not absolute.is_file():
                            continue
                        relative = absolute.relative_to(destination).as_posix()
                        safe = _safe_relative_path(relative)
                        if not safe:
                            continue
                        size = absolute.stat().st_size
                        if size > MAX_SINGLE_FILE:
                            continue
                        total += size
                        count += 1
                        if count > MAX_ARCHIVE_FILES or total > MAX_UNPACKED_BYTES:
                            raise RuntimeSandboxError("حجم المشروع المُصدّر تجاوز الحدود الآمنة.")
                        archive.write(absolute, safe)
            raw = buffer.getvalue()
            if len(raw) > MAX_EXPORT_BYTES:
                raise RuntimeSandboxError("نسخة المشروع أكبر من الحد المسموح للتنزيل.")
            item.last_used = time.time()
            return raw

    def stop(self, user_id: str | int, session_id: str) -> bool:
        item = self._get_owned(user_id, session_id)
        with self._lock:
            self._stop_locked(item.session_id)
        return True

    def status_for(self, user_id: str | int, session_id: str) -> dict[str, Any]:
        item = self._get_owned(user_id, session_id)
        remote_status = "unknown"
        try:
            remote = self._make_client().sandboxes.from_id(item.sandbox_id)
            remote_status = str(getattr(remote, "status", "unknown"))
            if remote_status in {"terminated", "errored"}:
                with self._lock:
                    self._sessions.pop(item.session_id, None)
                return {"active": False, "session_id": item.session_id, "logs": item.logs[-20:], "remote_status": remote_status}
        except Exception:
            remote_status = "unavailable"
        return {
            "active": True, "session_id": item.session_id, "logs": item.logs[-20:],
            "expires_in_seconds": max(0, SESSION_TTL_SECONDS - int(time.time() - item.last_used)),
            "remote_status": remote_status,
        }

    def shutdown_all(self) -> None:
        self._sweeper_stop.set()
        with self._lock:
            for sid in list(self._sessions):
                self._stop_locked(sid)


class RuntimeSandboxRouter:
    """Select the local namespace backend or managed Render backend by deployment config."""

    def __init__(self) -> None:
        if os.environ.get("ALPHA_RUNTIME_BACKEND", "local").strip().lower() == "render":
            self._backend = RenderRuntimeSandboxManager()
        else:
            self._backend = RuntimeSandboxManager()

    def capability_status(self):
        return self._backend.capability_status()

    def start(self, *args, **kwargs):
        return self._backend.start(*args, **kwargs)

    def execute(self, *args, **kwargs):
        return self._backend.execute(*args, **kwargs)

    def export(self, *args, **kwargs):
        return self._backend.export(*args, **kwargs)

    def stop(self, *args, **kwargs):
        return self._backend.stop(*args, **kwargs)

    def status_for(self, *args, **kwargs):
        return self._backend.status_for(*args, **kwargs)

    def shutdown_all(self):
        self._backend.shutdown_all()


runtime_sandbox = RuntimeSandboxRouter()
