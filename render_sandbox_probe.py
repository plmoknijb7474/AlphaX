#!/usr/bin/env python3
"""One-time live smoke test for Render Sandboxes. Creates and then terminates one sandbox.

Required environment: RENDER_API_KEY, RENDER_WORKSPACE_ID.
Optional: RENDER_SANDBOX_GROUP_ID.
No application/database secrets are forwarded to the sandbox.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def collect(client, sandbox_id: str, command: str) -> tuple[int | None, str, str]:
    stdout, stderr, exit_code = [], [], None
    for event in client.sandboxes.exec(sandbox_id, command):
        if isinstance(event, dict) and "exit_code" in event:
            exit_code = int(event["exit_code"])
        elif hasattr(event, "exit_code"):
            exit_code = int(event.exit_code)
        else:
            stream = event.get("stream") if isinstance(event, dict) else getattr(event, "stream", None)
            data = event.get("data", "") if isinstance(event, dict) else getattr(event, "data", "")
            (stderr if stream == "stderr" else stdout).append(str(data or ""))
    return exit_code, "".join(stdout), "".join(stderr)


def main() -> int:
    if not os.environ.get("RENDER_API_KEY") or not os.environ.get("RENDER_WORKSPACE_ID"):
        print("Missing RENDER_API_KEY or RENDER_WORKSPACE_ID. Set them in the environment; do not paste them into chat.")
        return 2
    try:
        from render import Render
    except Exception:
        print("Render SDK missing. Install requirements.txt (render>=1.8.0).")
        return 2

    client = Render(
        token=os.environ["RENDER_API_KEY"],
        owner_id=os.environ["RENDER_WORKSPACE_ID"],
    )
    sandbox = None
    checks: dict[str, bool] = {}
    result_code = 1
    cleanup_ok = False
    try:
        kwargs = {
            "plan": os.environ.get("RENDER_SANDBOX_PLAN", "1c-2g"),
            "timeout_seconds": 60,
            "idle_timeout_seconds": 300,
            "network_policy": "deny-all",
            "wait": True,
        }
        group_id = os.environ.get("RENDER_SANDBOX_GROUP_ID", "").strip()
        if group_id:
            kwargs["sandbox_group_id"] = group_id
        sandbox = client.sandboxes.create(**kwargs)
        command = (
            "mkdir -p /home/render/workspace && cd /home/render/workspace && "
            "timeout --signal=TERM --kill-after=2s 20s bash -c "
            "'printf ALPHA_RENDER_COMMAND_OK\\n'"
        )
        code, out, err = collect(client, sandbox.id, command)
        checks["command_timeout_wrapper"] = code == 0 and "ALPHA_RENDER_COMMAND_OK" in out
        print("command_timeout_wrapper:", "PASS" if checks["command_timeout_wrapper"] else "FAIL")
        if not checks["command_timeout_wrapper"]:
            print("stdout:", out[:500], "stderr:", err[:500])

        python_command = (
            "python3 --version && python3 -m venv /tmp/alpha-probe-venv && "
            "/tmp/alpha-probe-venv/bin/python -c \"print('ALPHA_RENDER_PYTHON_OK')\" && "
            "/tmp/alpha-probe-venv/bin/python -m pip --version"
        )
        python_code, python_out, python_err = collect(client, sandbox.id, python_command)
        checks["python_and_venv"] = python_code == 0 and "ALPHA_RENDER_PYTHON_OK" in python_out
        print("python_and_venv:", "PASS" if checks["python_and_venv"] else "FAIL")
        if not checks["python_and_venv"]:
            print("stdout:", python_out[:500], "stderr:", python_err[:500])

        with tempfile.TemporaryDirectory(prefix="alpha-render-probe-") as temp:
            local_file = Path(temp) / "alpha-probe.txt"
            local_file.write_text("alpha-render-copy-ok", encoding="utf-8")
            client.sandboxes.copy_to(sandbox.id, str(local_file), "/home/render/alpha-probe.txt")
            downloaded = Path(temp) / "downloaded.txt"
            client.sandboxes.copy_from(sandbox.id, "/home/render/alpha-probe.txt", str(downloaded))
            checks["file_transfer"] = downloaded.is_file() and downloaded.read_text(encoding="utf-8") == "alpha-render-copy-ok"
        print("file_transfer:", "PASS" if checks["file_transfer"] else "FAIL")

        network_code, network_out, _network_err = collect(
            client,
            sandbox.id,
            "python3 -c \"import socket,sys; s=socket.socket(); s.settimeout(2); r=s.connect_ex(('1.1.1.1',443)); print('NETWORK_BLOCKED' if r else 'NETWORK_ALLOWED'); sys.exit(0 if r else 3)\"",
        )
        checks["network_denied"] = network_code == 0 and "NETWORK_BLOCKED" in network_out
        print("network_denied:", "PASS" if checks["network_denied"] else "FAIL")
        if not checks["network_denied"]:
            print("network test output:", network_out[:300])

        print("region:", getattr(sandbox, "region", "provider default (currently Oregon)"))
        result_code = 0 if all(checks.values()) else 1
    except Exception as exc:
        print("Render Sandbox smoke test failed:", type(exc).__name__)
        result_code = 1
    finally:
        if sandbox is not None:
            try:
                client.sandboxes.terminate(sandbox.id)
                cleanup_ok = True
                print("sandbox_cleanup: PASS")
            except Exception:
                print("sandbox_cleanup: FAIL — check the Render dashboard for a leftover test sandbox")
        else:
            print("sandbox_cleanup: NOT RUN — no sandbox was created")
    return 0 if result_code == 0 and cleanup_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
