# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from .common import AiAgentCase


class TestAiAgentSkills(AiAgentCase):
    def setUp(self):
        super().setUp()
        self.skill = self.env["ai.skill"].create(
            {
                "name": "test_system_skill",
                "description": "Preloaded skill",
                "content": "Instructions for test skill.",
            }
        )
        self.on_demand_skill = self.env["ai.skill"].create(
            {
                "name": "test_on_demand_skill",
                "description": "Skill loaded on demand",
                "content": "Loaded only when asked.",
            }
        )
        self.tool = self._add_tool("get_uid", "_ai_get_uid")
        self.agent.write(
            {
                "system_prompt": "You are a helpful assistant.",
                "skill_ids": [(6, 0, [self.skill.id])],
                "tool_ids": [
                    (4, self.skill.tool_id.id),
                    (4, self.on_demand_skill.tool_id.id),
                ],
            }
        )

    def test_system_prompt_concatenation(self):
        prompt = self.agent._ai_get_system_prompt()
        self.assertTrue(prompt.startswith("You are a helpful assistant."))
        self.assertIn("--- PRELOADED SKILLS ---", prompt)
        self.assertIn("### Skill: test_system_skill", prompt)
        self.assertIn("Instructions for test skill.", prompt)
        self.assertNotIn("Loaded only when asked.", prompt)

    def test_system_prompt_without_skills(self):
        self.agent.skill_ids = False
        self.assertEqual(
            self.agent._ai_get_system_prompt(), "You are a helpful assistant."
        )

    def test_turn_uses_preloaded_skills(self):
        channel = self._create_agent_channel()
        with self._patch_run(lambda *a, **k: ("answer", 0, 0, 1)) as run:
            self._post(channel, "Hola agente")
            self._run_worker()
        kwargs = run.call_args.kwargs
        self.assertIn("Instructions for test skill.", kwargs["messages"][0]["content"])
        # The preloaded skill is not offered again as a tool, the others are
        self.assertEqual(kwargs["tools"], self.tool | self.on_demand_skill.tool_id)
