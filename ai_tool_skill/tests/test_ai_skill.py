# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase


class TestAiSkill(TransactionCase):
    def test_ai_skill_inherits_tool_lifecycle(self):
        # 1. Test creation of ai.skill via _inherits automatically creates ai.tool
        skill = self.env["ai.skill"].create(
            {
                "name": "test_skill_orm",
                "description": "Guide for optimizing ORM calls in Odoo",
                "content": "# ORM Optimization\n"
                "Use search_count instead of len(search).",
            }
        )
        self.assertTrue(skill.tool_id)
        tool = skill.tool_id
        self.assertEqual(tool.name, "test_skill_orm")
        self.assertEqual(tool.description, "Guide for optimizing ORM calls in Odoo")
        self.assertEqual(tool.skill_id, skill)

        # 2. Test tool execution returns skill content
        res = tool._execute_tool()
        self.assertEqual(res["name"], "test_skill_orm")
        self.assertEqual(
            res["content"],
            "# ORM Optimization\n" "Use search_count instead of len(search).",
        )

        # 3. Test update of skill delegates to tool automatically
        skill.write(
            {
                "name": "test_skill_orm_updated",
                "description": "Updated guide for ORM",
            }
        )
        self.assertEqual(tool.name, "test_skill_orm_updated")
        self.assertEqual(tool.description, "Updated guide for ORM")

        # 4. Test tool definition
        definition = tool._get_tool_definition()
        self.assertEqual(definition["name"], "test_skill_orm_updated")
        self.assertEqual(definition["description"], "Updated guide for ORM")

        # 5. Test deletion of skill unlinks delegated tool via cascade
        tool_id = tool.id
        skill.unlink()
        self.assertFalse(self.env["ai.tool"].browse(tool_id).exists())
