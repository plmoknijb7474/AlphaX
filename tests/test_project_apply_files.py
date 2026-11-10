import io
import unittest
import zipfile

from alpha_workspace import ProjectArchiveError, prepare_archive_with_generated_files


def make_zip(files):
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return target.getvalue()


class ProjectApplyFilesTests(unittest.TestCase):
    def test_replaces_and_adds_files_while_preserving_unrelated_entries(self):
        original = make_zip({
            "app.py": "print('old')\n",
            "LICENSE": "license text\n",
            "assets/logo.txt": "keep me\n",
        })
        updated, preview = prepare_archive_with_generated_files(original, [
            {"path": "app.py", "content": "print('new')\n"},
            {"path": "README.md", "content": "# Project\n"},
        ])
        self.assertEqual(len(preview), 2)
        self.assertEqual(preview[0]["status"], "updated")
        self.assertEqual(preview[1]["status"], "added")
        with zipfile.ZipFile(io.BytesIO(updated)) as archive:
            self.assertEqual(archive.read("app.py"), b"print('new')\n")
            self.assertEqual(archive.read("README.md"), b"# Project\n")
            self.assertEqual(archive.read("LICENSE"), b"license text\n")
            self.assertEqual(archive.read("assets/logo.txt"), b"keep me\n")
        with zipfile.ZipFile(io.BytesIO(original)) as archive:
            self.assertEqual(archive.read("app.py"), b"print('old')\n")

    def test_identical_file_is_reported_unchanged(self):
        original = make_zip({"main.py": "print('same')\n"})
        _updated, preview = prepare_archive_with_generated_files(original, [
            {"path": "main.py", "content": "print('same')\n"},
        ])
        self.assertEqual(preview[0]["status"], "unchanged")
        self.assertEqual(preview[0]["added"], 0)
        self.assertEqual(preview[0]["removed"], 0)

    def test_rejects_path_traversal_and_noncanonical_path(self):
        original = make_zip({"main.py": "print('ok')\n"})
        for path in ("../escape.py", "src/../escape.py", "src//main.py"):
            with self.subTest(path=path):
                with self.assertRaises(ProjectArchiveError):
                    prepare_archive_with_generated_files(original, [{"path": path, "content": "x"}])

    def test_rejects_secret_files(self):
        original = make_zip({"main.py": "print('ok')\n"})
        with self.assertRaises(ProjectArchiveError):
            prepare_archive_with_generated_files(original, [{"path": ".env", "content": "TOKEN=secret"}])

    def test_rejects_invalid_generated_python_before_applying(self):
        original = make_zip({"main.py": "print('ok')\n"})
        with self.assertRaises(ProjectArchiveError):
            prepare_archive_with_generated_files(original, [{"path": "main.py", "content": "def broken(:\n"}])

    def test_rejects_empty_file_list_and_invalid_zip(self):
        with self.assertRaises(ProjectArchiveError):
            prepare_archive_with_generated_files(make_zip({"a.txt": "a"}), [])
        with self.assertRaises(ProjectArchiveError):
            prepare_archive_with_generated_files(b"not-a-zip", [{"path": "a.txt", "content": "a"}])

    def test_rejects_file_directory_collision(self):
        original = make_zip({"src/existing.py": "print('ok')\n"})
        with self.assertRaises(ProjectArchiveError):
            prepare_archive_with_generated_files(original, [{"path": "src", "content": "not-a-directory"}])


    def test_supports_readme_requirements_and_docker_configuration_files(self):
        original = make_zip({"app.py": "print('ok')\n"})
        updated, preview = prepare_archive_with_generated_files(original, [
            {"path": "README.md", "content": "# Alpha\n"},
            {"path": "requirements.txt", "content": "flask==3.0.0\n"},
            {"path": "Dockerfile", "content": "FROM python:3.12-slim\n"},
            {"path": ".dockerignore", "content": ".git\n.venv\n"},
        ])
        self.assertEqual([item["status"] for item in preview], ["added"] * 4)
        with zipfile.ZipFile(io.BytesIO(updated)) as archive:
            self.assertEqual(archive.read("README.md"), b"# Alpha\n")
            self.assertEqual(archive.read("requirements.txt"), b"flask==3.0.0\n")
            self.assertEqual(archive.read("Dockerfile"), b"FROM python:3.12-slim\n")
            self.assertEqual(archive.read(".dockerignore"), b".git\n.venv\n")

    def test_rejects_replacement_that_exceeds_uncompressed_archive_limit(self):
        from unittest.mock import patch
        with patch("alpha_workspace.MAX_TOTAL_UNCOMPRESSED", 1000):
            original = make_zip({"large.txt": "x" * 900})
            with self.assertRaises(ProjectArchiveError):
                prepare_archive_with_generated_files(original, [
                    {"path": "large.txt", "content": "y" * 1100}
                ])


if __name__ == "__main__":
    unittest.main()
