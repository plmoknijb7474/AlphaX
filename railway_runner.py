"""Private Railway service that hosts Alpha's fail-closed Linux sandbox runner.

Deploy this as a separate, non-public Railway service. It must not receive the
web application's database URL, Flask secret, or AI-provider credentials.
"""
from __future__ import annotations

import atexit
import hmac
import logging
import os
from functools import wraps
from io import BytesIO
from typing import Callable

from flask import Flask, jsonify, request, send_file

from runtime_sandbox import RuntimeSandboxError, runtime_sandbox, MAX_UPLOAD_BYTES

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("alpha.railway_runner")

if os.environ.get("ALPHA_RUNTIME_BACKEND", "local").strip().lower() != "local":
    raise RuntimeError("alpha-runner must use ALPHA_RUNTIME_BACKEND=local for its internal Linux namespace engine.")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES + (1024 * 1024)
manager = runtime_sandbox
atexit.register(manager.shutdown_all)


def _authorized() -> bool:
    expected = os.environ.get("ALPHA_RUNNER_TOKEN", "").strip()
    supplied = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not expected or len(expected) < 32 or not supplied.startswith(prefix):
        return False
    return hmac.compare_digest(supplied[len(prefix):], expected)


def require_internal_token(view: Callable):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _authorized():
            return jsonify(error="Unauthorized"), 401
        return view(*args, **kwargs)
    return wrapped


@app.get("/internal/healthz")
def healthz():
    # Liveness only. Sandbox capability is reported separately and fails closed.
    return jsonify(status="ok", service="alpha-runner"), 200


@app.get("/internal/runtime/status")
@require_internal_token
def runtime_status():
    status = manager.capability_status()
    status["runner"] = "alpha-runner"
    return jsonify(status), 200


@app.post("/internal/runtime/start")
@require_internal_token
def runtime_start():
    user_id = str(request.form.get("user_id", "")).strip()
    if not user_id or len(user_id) > 128:
        return jsonify(error="Invalid user identifier"), 400
    try:
        started = manager.start(user_id, request.files.getlist("files"))
        return jsonify(ok=True, **started), 201
    except RuntimeSandboxError as exc:
        status = manager.capability_status()
        code = 503 if not status.get("ready") else 400
        return jsonify(error=str(exc), sandbox=status), code
    except Exception as exc:
        logger.warning("Runner start failed (%s)", type(exc).__name__)
        return jsonify(error="تعذر بدء مساحة التنفيذ المعزولة."), 500


@app.post("/internal/runtime/execute")
@require_internal_token
def runtime_execute():
    data = request.get_json(silent=True) or {}
    user_id = str(data.get("user_id", "")).strip()
    if not user_id or len(user_id) > 128:
        return jsonify(error="Invalid user identifier"), 400
    try:
        result = manager.execute(
            user_id, data.get("session_id", ""), data.get("action", ""),
            command=data.get("command", ""), path=data.get("path", ""),
            packages=data.get("packages", []),
        )
        return jsonify(ok=True, **result), 200
    except RuntimeSandboxError as exc:
        return jsonify(error=str(exc)), 400
    except Exception as exc:
        logger.warning("Runner execution failed (%s)", type(exc).__name__)
        return jsonify(error="تعذر تنفيذ العملية داخل بيئة التنفيذ المعزولة."), 500


@app.get("/internal/runtime/session")
@require_internal_token
def runtime_session():
    user_id = str(request.args.get("user_id", "")).strip()
    session_id = request.args.get("session_id", "")
    if not user_id or len(user_id) > 128:
        return jsonify(error="Invalid user identifier"), 400
    try:
        return jsonify(manager.status_for(user_id, session_id)), 200
    except RuntimeSandboxError as exc:
        return jsonify(error=str(exc), active=False), 404
    except Exception as exc:
        logger.warning("Runner session status failed (%s)", type(exc).__name__)
        return jsonify(error="تعذر قراءة حالة جلسة التنفيذ."), 500


@app.get("/internal/runtime/export")
@require_internal_token
def runtime_export():
    user_id = str(request.args.get("user_id", "")).strip()
    session_id = request.args.get("session_id", "")
    if not user_id or len(user_id) > 128:
        return jsonify(error="Invalid user identifier"), 400
    try:
        archive = manager.export(user_id, session_id)
        return send_file(
            BytesIO(archive), mimetype="application/zip", as_attachment=True,
            download_name="Alpha-Runtime-Workspace.zip", max_age=0,
        )
    except RuntimeSandboxError as exc:
        return jsonify(error=str(exc)), 400
    except Exception as exc:
        logger.warning("Runner export failed (%s)", type(exc).__name__)
        return jsonify(error="تعذر تصدير مساحة التنفيذ."), 500


@app.post("/internal/runtime/stop")
@require_internal_token
def runtime_stop():
    data = request.get_json(silent=True) or {}
    user_id = str(data.get("user_id", "")).strip()
    if not user_id or len(user_id) > 128:
        return jsonify(error="Invalid user identifier"), 400
    try:
        manager.stop(user_id, data.get("session_id", ""))
        return jsonify(ok=True), 200
    except RuntimeSandboxError as exc:
        return jsonify(error=str(exc)), 400
    except Exception as exc:
        logger.warning("Runner stop failed (%s)", type(exc).__name__)
        return jsonify(error="تعذر إغلاق جلسة التنفيذ."), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
