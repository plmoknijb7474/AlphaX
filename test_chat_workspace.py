import pytest

from chat_workspace import (
    MAX_WORKSPACE_FILE_BYTES,
    WorkspaceValidationError,
    normalize_workspace_content,
    normalize_workspace_filename,
)


@pytest.mark.parametrize("name, expected", [
    ("README.md", "README.md"),
    ("src/main.py", "src/main.py"),
    ("ملاحظات/الخطة.txt", "ملاحظات/الخطة.txt"),
    (".env.example", ".env.example"),
    (".gitignore", ".gitignore"),
])
def test_safe_workspace_names(name, expected):
    assert normalize_workspace_filename(name) == expected


@pytest.mark.parametrize("name", [
    "", "../outside.txt", "src/../../outside.txt", "/absolute.txt",
    "src\\main.py", "folder//file.txt", "folder/./file.txt",
    ".env", ".env.local", "secrets/passwords.txt", "id_rsa",
    "private/cert.pem", "token_store.json", "config.key",
])
def test_reject_unsafe_workspace_names(name):
    with pytest.raises(WorkspaceValidationError):
        normalize_workspace_filename(name)


def test_workspace_content_must_be_text_and_utf8_safe():
    assert normalize_workspace_content("مرحبا\nprint('ok')") == "مرحبا\nprint('ok')"
    with pytest.raises(WorkspaceValidationError):
        normalize_workspace_content(b"binary")
    with pytest.raises(WorkspaceValidationError):
        normalize_workspace_content("bad\x00text")


def test_workspace_content_size_limit():
    assert len(normalize_workspace_content("x" * MAX_WORKSPACE_FILE_BYTES)) == MAX_WORKSPACE_FILE_BYTES
    with pytest.raises(WorkspaceValidationError):
        normalize_workspace_content("x" * (MAX_WORKSPACE_FILE_BYTES + 1))
