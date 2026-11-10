import unittest

from project_toolbox import (
    DEFAULT_PROJECT_TOOLS,
    PROJECT_TOOL_GUIDANCE,
    build_project_reviewer_tool_section,
    build_project_tool_prompt_section,
    parse_project_tool_flags,
)


class ProjectToolboxTests(unittest.TestCase):
    def test_defaults_are_valid_and_cover_core_workflows(self):
        self.assertTrue(set(DEFAULT_PROJECT_TOOLS).issubset(PROJECT_TOOL_GUIDANCE))
        self.assertIn("code_generation", DEFAULT_PROJECT_TOOLS)
        self.assertIn("code_testing", DEFAULT_PROJECT_TOOLS)

    def test_parses_json_and_deduplicates(self):
        self.assertEqual(
            parse_project_tool_flags('["code_generation", "debugging", "debugging"]'),
            ["code_generation", "debugging"],
        )

    def test_rejects_unknown_values(self):
        self.assertEqual(parse_project_tool_flags(["code_generation", "shell", None, 2]), ["code_generation"])
        self.assertEqual(parse_project_tool_flags("not-json"), [])

    def test_prompt_only_contains_selected_workflows(self):
        prompt = build_project_tool_prompt_section(["readme_generator", "docker_configuration"])
        self.assertIn("README Generator", prompt)
        self.assertIn("Docker Configuration", prompt)
        self.assertNotIn("Code Generation:", prompt)
        self.assertIn("Do not execute uploaded code", prompt)

    def test_prompt_empty_when_no_workflows(self):
        self.assertEqual(build_project_tool_prompt_section([]), "")

    def test_reviewer_gets_selected_tool_list(self):
        prompt = build_project_reviewer_tool_section(["code_testing", "apply_patch", "debugging"])
        self.assertIn("code_testing", prompt)
        self.assertIn("debugging", prompt)
        self.assertNotIn("apply_patch", prompt)


if __name__ == "__main__":
    unittest.main()
