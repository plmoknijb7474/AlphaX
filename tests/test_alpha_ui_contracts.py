import ast
import re
import unittest
from pathlib import Path

from bs4 import BeautifulSoup
from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]


def template_from_app(name):
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source, filename="app.py")
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                return ast.literal_eval(node.value)
    raise AssertionError(f"Template {name} was not found")


def render_template(name, **context):
    env = Environment(autoescape=True)
    env.globals["url_for"] = lambda endpoint, **kwargs: "/" + endpoint.replace("_", "-")
    env.globals["get_flashed_messages"] = lambda: []
    return env.from_string(template_from_app(name)).render(**context)


class AlphaUIContractTests(unittest.TestCase):
    def test_workbench_has_five_modes_and_defaults_off(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("security_review", app)
        self.assertNotIn("مراجعة الأمان", app)
        self.assertIn('id="studioCount">0/5', app)
        self.assertIn("let codingToolState = Object.fromEntries(CODING_TOOL_KEYS.map(key => [key, false]));", app)
        self.assertEqual(len(re.findall(r'data-coding-tool="[a-z_]+" aria-pressed="false"', app)), 5)

    def test_project_timeline_completed_connectors_are_green(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn(".pi-timeline-step.is-connected:before{transform:scaleX(1);background:#22c55e", app)

    def test_project_intelligence_settings_are_at_bottom_of_task_form(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        task = app.index('id="piTask"')
        settings = app.index('id="piSettingsDrawer"')
        run = app.index('id="piRunBtn"')
        self.assertLess(task, settings)
        self.assertLess(settings, run)
        self.assertIn("لا يعرض Alpha تكلفة مالية تقديرية حالياً", app)
        self.assertIn('id="piWriterModel"', app)
        self.assertIn('id="piReviewerModel"', app)
        self.assertIn('id="piCycles"', app)
        self.assertIn('id="piReasoningToggle"', app)

    def test_chat_and_login_templates_render_with_unique_ids(self):
        cases = [
            ("CHAT_HTML", dict(username="audit-user", csrf_token="test", subscription_active=True)),
            ("LOGIN_HTML", dict(mode="register", csrf_token="test")),
        ]
        for template_name, context in cases:
            with self.subTest(template=template_name):
                html = render_template(template_name, **context)
                soup = BeautifulSoup(html, "html.parser")
                ids = [tag.get("id") for tag in soup.find_all(attrs={"id": True})]
                duplicates = sorted({item for item in ids if ids.count(item) > 1})
                self.assertEqual(duplicates, [])
                self.assertGreater(len(ids), 5)

    def test_integrated_login_uses_username_password_and_confirmation_only(self):
        html = render_template("LOGIN_HTML", mode="register", csrf_token="test")
        soup = BeautifulSoup(html, "html.parser")
        names = {field.get("name") for field in soup.select("input[name]")}
        self.assertTrue({"username", "password", "confirmPassword"}.issubset(names))
        self.assertNotIn("email", names)
        self.assertTrue(all(form.get("method", "get").lower() == "post" for form in soup.find_all("form")))

    def test_public_readme_uses_alpha_branding_without_provider_names(self):
        readme = (ROOT / "README-ar.txt").read_text(encoding="utf-8").lower()
        for hidden in ("xkiro", "token harbor", "qwen/", "gemma-"):
            self.assertNotIn(hidden, readme)


if __name__ == "__main__":
    unittest.main()
