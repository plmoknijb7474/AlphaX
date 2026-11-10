import unittest
from pathlib import Path


class SandboxDeploymentConfigTests(unittest.TestCase):
    def test_railway_web_and_runner_dockerfiles_exist(self):
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / "Dockerfile").is_file())
        self.assertTrue((root / "Dockerfile.runner").is_file())
        self.assertTrue((root / "railway_runner.py").is_file())
        self.assertFalse((root / "render.yaml").exists())
        self.assertFalse((root / "render_sandbox_probe.py").exists())

    def test_legacy_render_sdk_is_not_a_runtime_dependency(self):
        root = Path(__file__).resolve().parents[1]
        requirements = (root / "requirements.txt").read_text(encoding="utf-8").lower()
        self.assertNotIn("render>=", requirements)
        runner_requirements = (root / "requirements-runner.txt").read_text(encoding="utf-8").lower()
        self.assertIn("flask", runner_requirements)
        self.assertIn("requests", runner_requirements)

    def test_railway_is_the_remote_sandbox_backend(self):
        root = Path(__file__).resolve().parents[1]
        runtime = (root / "runtime_sandbox.py").read_text(encoding="utf-8")
        runner = (root / "railway_runner.py").read_text(encoding="utf-8")
        self.assertIn('selected == "railway"', runtime)
        self.assertIn("ALPHA_RUNNER_URL", runtime)
        self.assertIn("ALPHA_RUNNER_TOKEN", runtime)
        self.assertIn("manager = runtime_sandbox", runner)
        self.assertIn("ALPHA_RUNTIME_BACKEND=local", runner)
        self.assertIn("require_internal_token", runner)
        self.assertIn("hmac.compare_digest", runner)

    def test_railway_deployment_guide_explains_private_runner(self):
        root = Path(__file__).resolve().parents[1]
        guide = (root / "DEPLOY-RAILWAY-SUPABASE-AR.md").read_text(encoding="utf-8")
        self.assertIn("alpha-runner.railway.internal", guide)
        self.assertIn("Dockerfile.runner", guide)
        self.assertIn("ready=true", guide)
        self.assertIn("لا يحتاج التطبيق إلى `RAILWAY_API_TOKEN`", guide)


if __name__ == "__main__":
    unittest.main()
