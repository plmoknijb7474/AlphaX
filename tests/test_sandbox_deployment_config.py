import re
import unittest
from pathlib import Path


class SandboxDeploymentConfigTests(unittest.TestCase):
    def test_render_blueprint_enables_managed_sandboxes(self):
        root = Path(__file__).resolve().parents[1]
        config = (root / "render.yaml").read_text(encoding="utf-8")
        backend = re.findall(
            r"(?m)^\s*- key: ALPHA_RUNTIME_BACKEND\s*\n\s*value: ([^\s]+)\s*$",
            config,
        )
        enabled = re.findall(
            r"(?m)^\s*- key: ALPHA_SANDBOX_ENABLED\s*\n\s*value: \"([^\"]+)\"\s*$",
            config,
        )
        self.assertEqual(backend, ["render"])
        self.assertEqual(enabled, ["1"])


if __name__ == "__main__":
    unittest.main()
