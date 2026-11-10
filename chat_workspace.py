"""Validation helpers for per-conversation text workspaces."""
from __future__ import annotations

import re
from pathlib import PurePosixPath

MAX_WORKSPACE_FILENAME = 180
MAX_WORKSPACE_FILE_BYTES = 2 * 1024 * 1024
MAX_WORKSPACE_FILES = 200
MAX_WORKSPACE_TOTAL_BYTES = 20 * 1024 * 1024

_SECRET_NAMES = {
    ".env", ".env.local", ".env.production", ".env.development",
    "id_rsa", "id_ed25519", "credentials.json", "service-account.json",
    "secrets.json", "token.json", ".npmrc", ".pypirc", ".netrc",
    ".api_encryption.key", ".flask_secret_key", "app.db", "database.db",
    "known_hosts", "authorized_keys",
}
_SECRET_DIRS = {".aws", ".ssh", ".gnupg", "secrets", "private", "credentials"}
_SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore", ".jks"}
_SECRET_HINTS = ("service-account", "credential", "secret", "private_key", "secret_key", "token_store")
_ALLOWED_ENV_TEMPLATES = {".env.example", ".env.sample", ".env.template"}


class WorkspaceValidationError(ValueError):
    """Raised when a workspace filename or text payload is unsafe or too large."""


def normalize_workspace_filename(value: object) -> str:
    if not isinstance(value, str):
        raise WorkspaceValidationError("اسم الملف غير صالح.")
    name = value.strip()
    if not name or len(name) > MAX_WORKSPACE_FILENAME:
        raise WorkspaceValidationError("اسم الملف مطلوب ويجب ألا يتجاوز 180 حرفاً.")
    if "\\" in name or name.startswith("/") or "\x00" in name:
        raise WorkspaceValidationError("مسار الملف غير آمن.")
    raw_parts = name.split("/")
    if any(part in ("", ".", "..") for part in raw_parts):
        raise WorkspaceValidationError("مسار الملف يجب أن يكون نسبياً ولا يحتوي على أجزاء غير آمنة.")
    if ":" in raw_parts[0] or any(re.search(r"[\x00-\x1f\x7f]", part) for part in raw_parts):
        raise WorkspaceValidationError("اسم الملف يحتوي محارف غير مسموحة.")
    path = PurePosixPath(name)
    lowered_parts = {part.casefold() for part in path.parts}
    lower_name = path.name.casefold()
    if (lower_name in _SECRET_NAMES
            or (lower_name.startswith(".env") and lower_name not in _ALLOWED_ENV_TEMPLATES)
            or any(part in _SECRET_DIRS for part in lowered_parts)
            or path.suffix.casefold() in _SECRET_SUFFIXES
            or any(hint in lower_name for hint in _SECRET_HINTS)):
        raise WorkspaceValidationError("لا يمكن حفظ ملفات الأسرار أو المفاتيح أو بيانات الاعتماد في Workspace.")
    return path.as_posix()


def normalize_workspace_content(value: object) -> str:
    if not isinstance(value, str):
        raise WorkspaceValidationError("محتوى الملف يجب أن يكون نصاً.")
    if "\x00" in value:
        raise WorkspaceValidationError("الملفات الثنائية غير مدعومة في Workspace.")
    if len(value.encode("utf-8")) > MAX_WORKSPACE_FILE_BYTES:
        raise WorkspaceValidationError("حجم الملف يتجاوز 2 ميغابايت.")
    return value
