"""Dependency-light regression tests for the Alpha Max Qwen fallback chain."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = ROOT / "app.py"


class _Cipher:
    @staticmethod
    def encrypt(value: str) -> str:
        return "encrypted:" + value


class _Logger:
    @staticmethod
    def warning(*_args, **_kwargs) -> None:
        return None

    @staticmethod
    def debug(*_args, **_kwargs) -> None:
        return None


def _load_routing_functions():
    tree = ast.parse(APP_SOURCE.read_text(encoding="utf-8"), filename="app.py")
    names = {
        "ALPHA_MAX_MODEL",
        "ALPHA_MAX_FALLBACK_MODEL",
        "XKIRO_BASE_URL",
        "MAX_API_KEYS_PER_MODEL",
        "LONG_MODEL",
    }
    wanted_functions = {"parse_api_route_lines", "generate_with_api_failover"}
    body = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in names for target in node.targets
        ):
            body.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in wanted_functions:
            body.append(node)

    namespace = {
        "cipher": _Cipher(),
        "ChatCancelled": type("ChatCancelled", (Exception,), {}),
        "ensure_system_prompt_applied": lambda prompt, _model: prompt,
        "app": SimpleNamespace(logger=_Logger()),
    }
    exec(compile(ast.Module(body=body, type_ignores=[]), str(APP_SOURCE), "exec"), namespace)
    return namespace


def test_each_qwen_api_key_creates_primary_then_preview_fallback():
    ns = _load_routing_functions()
    routes = ns["parse_api_route_lines"]("test-key-123", ns["ALPHA_MAX_MODEL"])

    assert [route["upstream_model"] for route in routes] == [
        "qwen/qwen3.7-max:free",
        "qwen/qwen3.6-max-preview:free",
    ]
    assert all(route["provider"] == "xkiro" for route in routes)
    assert all(route["base_url"] == ns["XKIRO_BASE_URL"] for route in routes)
    assert routes[0]["api_key_enc"] == routes[1]["api_key_enc"] == "encrypted:test-key-123"


def test_failover_tries_preview_after_primary_failure_and_resets_stream():
    ns = _load_routing_functions()
    primary = {"provider": "xkiro", "upstream_model": "qwen/qwen3.7-max:free", "api_key": "secret"}
    fallback = {"provider": "xkiro", "upstream_model": "qwen/qwen3.6-max-preview:free", "api_key": "secret"}
    attempts = []
    resets = []

    def fake_call(route, *_args, **_kwargs):
        attempts.append(route["upstream_model"])
        if route["upstream_model"] == "qwen/qwen3.7-max:free":
            raise RuntimeError("simulated primary failure")
        return "fallback response", None, {"total_tokens": 7}

    ns["call_one_api_route"] = fake_call
    result = ns["generate_with_api_failover"](
        [primary, fallback],
        contents=[],
        system_prompt="test prompt",
        model_id=ns["ALPHA_MAX_MODEL"],
        thinking="high",
        on_reset=lambda: resets.append(True),
    )

    assert result == ("fallback response", None, {"total_tokens": 7}, 2)
    assert attempts == ["qwen/qwen3.7-max:free", "qwen/qwen3.6-max-preview:free"]
    assert resets == [True]
