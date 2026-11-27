# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from unittest.mock import patch

from pydantic import ValidationError

from odoo.tests.common import TransactionCase

from ..models.schemas import (
    ActionPlanPayload,
    ActionStep,
)


class NonSerializableObj:
    pass


class TestAiAgent(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_user = cls.env["res.users"].create(
            {
                "name": "Test AI Agent User",
                "login": "test_ai_agent_user",
                "email": "test_ai_agent@example.com",
                "is_ai_agent": True,
            }
        )
        cls.prompt_template = cls.env["ai.prompt.template"].create(
            {
                "name": "Test System Prompt",
                "code": "test_system_prompt_agent",
                "prompt_type": "system",
                "template_text": "You are a test AI agent: <t t-out='content'/>",
            }
        )
        cls.persona = cls.env["ai.persona"].create(
            {
                "name": "Test Agent Persona",
                "code": "test_agent_persona_code",
                "system_prompt_id": cls.prompt_template.id,
            }
        )

    def test_create_ai_agent_with_user_context_execution_mode(self):
        agent = self.env["ai.agent"].create(
            {
                "name": "Default User Context Agent",
                "persona_id": self.persona.id,
                "user_id": self.test_user.id,
                "execution_mode": "user_context",
            }
        )
        self.assertTrue(agent.active)
        self.assertEqual(agent.execution_mode, "user_context")
        self.assertEqual(agent.persona_id, self.persona)

    def test_create_ai_agent_with_dedicated_agent_user(self):
        agent = self.env["ai.agent"].create(
            {
                "name": "Dedicated Service Agent",
                "persona_id": self.persona.id,
                "user_id": self.test_user.id,
                "execution_mode": "dedicated_agent",
            }
        )
        self.assertEqual(agent.execution_mode, "dedicated_agent")
        self.assertEqual(agent.user_id, self.test_user)
        self.assertTrue(agent.user_id.is_ai_agent)

    def test_res_users_is_ai_agent_flag(self):
        self.assertTrue(self.test_user.is_ai_agent)
        standard_user = self.env["res.users"].create(
            {
                "name": "Human Standard User",
                "login": "human_standard_user",
                "email": "human@example.com",
            }
        )
        self.assertFalse(standard_user.is_ai_agent)

    def test_prompt_template_rendering(self):
        # 1. Standard QWeb rendering
        res = self.prompt_template.render(content="Hello World")
        self.assertIn("Hello World", res)

        # 2. Empty template text
        empty_template = self.env["ai.prompt.template"].create(
            {
                "name": "Empty Prompt",
                "code": "empty_prompt_code",
                "prompt_type": "system",
                "template_text": "   ",
            }
        )
        self.assertEqual(empty_template.render(), "")

        # 3. QWeb render error fallback to string format
        format_template = self.env["ai.prompt.template"].create(
            {
                "name": "Format Prompt",
                "code": "format_prompt_code",
                "prompt_type": "system",
                "template_text": "Hello {content}",
            }
        )
        with patch.object(
            type(self.env["ir.qweb"]),
            "_render",
            side_effect=ValueError("Invalid QWeb syntax"),
        ):
            rendered_format = format_template.render(content="Fallback String")
            self.assertEqual(rendered_format, "Hello Fallback String")

        # 4. QWeb render error fallback to raw template text when formatting also fails
        invalid_format_template = self.env["ai.prompt.template"].create(
            {
                "name": "Invalid Format Prompt",
                "code": "invalid_format_prompt_code",
                "prompt_type": "system",
                "template_text": "Hello {invalid_key_that_does_not_exist}",
            }
        )
        with patch.object(
            type(self.env["ir.qweb"]),
            "_render",
            side_effect=ValueError("Invalid QWeb syntax"),
        ):
            rendered_raw = invalid_format_template.render()
            self.assertEqual(rendered_raw, "Hello {invalid_key_that_does_not_exist}")

    def test_prompt_template_render_values_with_kwargs(self):
        partner = self.env["res.partner"].create({"name": "Test Partner"})
        vals = self.prompt_template._get_prompt_render_values(
            record=partner,
            record_chatter="Existing Chatter",
        )
        self.assertEqual(vals["record_chatter"], "Existing Chatter")
        self.assertEqual(vals["chatter_messages"], "Existing Chatter")

    def test_prompt_template_with_mocked_ai_thread(self):
        from unittest.mock import MagicMock

        partner = self.env["res.partner"].create({"name": "Test Partner"})
        mock_thread_model = MagicMock()
        mock_thread_model._get_record_context.return_value = {"name": partner.name}
        mock_thread_model._get_chatter_history_content.return_value = "Chatter text"

        orig_contains = type(self.env).__contains__
        orig_getitem = type(self.env).__getitem__

        def custom_contains(env_self, key):
            return key == "ai.thread" or orig_contains(env_self, key)

        def custom_getitem(env_self, key):
            return (
                mock_thread_model if key == "ai.thread" else orig_getitem(env_self, key)
            )

        with patch.object(type(self.env), "__contains__", custom_contains):
            with patch.object(type(self.env), "__getitem__", custom_getitem):
                # 1. Enabled flags with data
                vals = self.prompt_template._get_prompt_render_values(record=partner)
                self.assertIn("Test Partner", vals["record_context"])
                self.assertEqual(vals["record_chatter"], "Chatter text")

                # 2. Disabled flags
                self.prompt_template.write(
                    {
                        "include_record_data": False,
                        "include_record_chatter": False,
                    }
                )
                vals_disabled = self.prompt_template._get_prompt_render_values(
                    record=partner
                )
                self.assertEqual(vals_disabled["record_context"], "")

                # 3. Non-serializable context_data calling _safe_json_default
                mock_thread_model._get_record_context.return_value = {
                    "non_serializable": NonSerializableObj()
                }
                self.prompt_template.write(
                    {
                        "include_record_data": True,
                        "include_record_chatter": True,
                    }
                )
                vals_non_ser = self.prompt_template._get_prompt_render_values(
                    record=partner
                )
                self.assertIn("NonSerializableObj", vals_non_ser["record_context"])

        def no_ai_thread_contains(env_self, key):
            return False if key == "ai.thread" else orig_contains(env_self, key)

        with patch.object(type(self.env), "__contains__", no_ai_thread_contains):
            vals_no_thread = self.prompt_template._get_prompt_render_values(
                record=partner,
                record_chatter="Direct Chatter Text",
            )
            self.assertEqual(vals_no_thread["record_chatter"], "Direct Chatter Text")

    def test_pydantic_action_plan_schemas(self):
        step = ActionStep(
            step_id=1,
            objective="Mettre à jour le CRM Lead",
            target_type="tool",
            target_name="crm_lead_stage_update",
            params={"lead_id": 42},
            depends_on=[],
        )
        self.assertEqual(step.step_id, 1)
        self.assertEqual(step.target_type, "tool")

        plan = ActionPlanPayload(
            summary="Plan d'action de démonstration",
            steps=[step],
        )
        data = plan.model_dump()
        self.assertEqual(data["plan_version"], "1.0")
        self.assertEqual(data["summary"], "Plan d'action de démonstration")
        self.assertEqual(len(data["steps"]), 1)
        self.assertEqual(data["steps"][0]["target_name"], "crm_lead_stage_update")

        # Invalid target_type should raise ValidationError
        with self.assertRaises(ValidationError):
            ActionStep(
                step_id=2,
                objective="Action invalide",
                target_type="invalid_type",
                target_name="foo",
            )
