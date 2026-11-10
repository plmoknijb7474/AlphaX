#!/usr/bin/env python3
"""Verify a deployed Alpha HTTP endpoint and its database-backed health check."""
from __future__ import annotations

import json
import sys
from urllib.parse import urlparse


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python verify_alpha_deployment.py https://YOUR-SERVICE.onrender.com")
        return 2
    base = sys.argv[1].strip().rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" or not parsed.netloc:
        print("Use a valid HTTPS Render service URL.")
        return 2
    try:
        import requests
    except Exception:
        print("The requests package is missing. Install requirements.txt first.")
        return 2
    try:
        response = requests.get(base + "/healthz", timeout=20, headers={"Accept": "application/json"})
        try:
            body = response.json()
        except ValueError:
            body = {"status": "non-json response"}
        ok = response.status_code == 200 and body.get("status") == "ok"
        print(json.dumps({
            "ok": ok,
            "http_status": response.status_code,
            "health_status": body.get("status"),
            "test": "Flask/Gunicorn HTTP endpoint + live database SELECT 1",
        }, ensure_ascii=False))
        return 0 if ok else 1
    except requests.RequestException as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__, "message": "Could not reach the HTTPS health endpoint."}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
