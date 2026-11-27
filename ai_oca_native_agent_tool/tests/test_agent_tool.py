# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import json

from pydantic import ValidationError

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.ai_tool.tools import aitool


class TestAiAgentTool(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tool_get_date = cls.env.ref("ai_tool.current_date")
        cls.tool_post_message = cls.env.ref("ai_tool.post_message")
        cls.partner = cls.env["res.partner"].create({"name": "Partner Test Tool"})

        cls.tool_record_kind = cls.env["ai.tool"].create(
            {
                "name": "partner_custom_record_tool",
                "description": "Record kind test tool",
                "model_id": cls.env.ref("base.model_res_partner").id,
                "function_name": "_ai_test_record_method",
                "kind": "record",
            }
        )

        cls.restricted_user = cls.env["res.users"].create(
            {
                "name": "Restricted Agent User",
                "login": "restricted_agent_user",
                "email": "restricted@example.com",
                "is_ai_agent": True,
            }
        )
        cls.agent = cls.env["ai.agent"].create(
            {
                "name": "Tool Test Agent",
                "user_id": cls.restricted_user.id,
                "execution_mode": "user_context",
                "tool_ids": [
                    (
                        6,
                        0,
                        [
                            cls.tool_get_date.id,
                            cls.tool_post_message.id,
                            cls.tool_record_kind.id,
                        ],
                    )
                ],
            }
        )

    def test_get_openai_tools_definitions_returns_function_schemas(self):
        definitions = self.agent.get_openai_tools_definitions()
        self.assertEqual(len(definitions), 3)
        self.assertEqual(definitions[0]["type"], "function")
        names = [d["function"]["name"] for d in definitions]
        self.assertIn("get_date", names)
        self.assertIn("post_message", names)

    def test_get_openai_tools_definitions_filtered_by_tool_names(self):
        definitions = self.agent.get_openai_tools_definitions(
            tool_names=["post_message"]
        )
        self.assertEqual(len(definitions), 1)
        self.assertEqual(definitions[0]["function"]["name"], "post_message")

    def test_get_decision_tool_candidates_with_and_without_done(self):
        candidates_with_done = self.agent.get_decision_tool_candidates(
            include_done=True
        )
        values_with_done = [c["value"] for c in candidates_with_done]
        self.assertIn("get_date", values_with_done)
        self.assertIn("post_message", values_with_done)
        self.assertEqual(values_with_done[-1], "done")

        candidates_no_done = self.agent.get_decision_tool_candidates(include_done=False)
        values_no_done = [c["value"] for c in candidates_no_done]
        self.assertNotIn("done", values_no_done)
        self.assertEqual(len(values_no_done), 3)

    def test_tool_requires_arguments_detects_zero_arg_and_parameterized_tools(self):
        self.assertFalse(self.agent.tool_requires_arguments("get_date"))
        self.assertTrue(self.agent.tool_requires_arguments("post_message"))
        self.assertFalse(self.agent.tool_requires_arguments("unknown_tool"))

    def test_execute_tool_succeeds_for_allowed_tool(self):
        res = self.agent.execute_tool("get_date")
        self.assertIn("date", res)

    def test_execute_tool_raises_user_error_for_unallowed_tool(self):
        with self.assertRaises(UserError):
            self.agent.execute_tool("unallowed_tool_name")

    def test_execute_tool_under_dedicated_agent_security_context(self):
        self.agent.write(
            {
                "execution_mode": "dedicated_agent",
                "user_id": self.restricted_user.id,
            }
        )
        res = self.agent.execute_tool("get_date")
        self.assertIn("date", res)

    def test_execute_generic_model_tool_with_record(self):
        res = self.agent.execute_tool(
            "post_message",
            params={"message": "Hello Chatter"},
            record=self.partner,
        )
        self.assertEqual(res, {})

    def test_execute_non_generic_tool_without_record_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.agent.execute_tool("post_message", params={"message": "No record"})

    def test_execute_record_kind_tool_with_mismatched_model_raises_value_error(self):
        company = self.env["res.company"].create({"name": "Test Company"})
        with self.assertRaises(ValueError):
            self.agent.execute_tool(
                "partner_custom_record_tool",
                record=company,
            )

    def test_execute_record_kind_tool_succeeds(self):
        # Dynamically attach test method to res.partner model
        def _dummy_record_tool(partner_self):
            return {"partner_name": partner_self.name}

        type(self.partner)._ai_test_record_method = aitool({}, {})(_dummy_record_tool)

        res = self.agent.execute_tool(
            "partner_custom_record_tool",
            record=self.partner,
        )
        self.assertEqual(res.get("partner_name"), "Partner Test Tool")

    def test_agent_list_available_tools(self):
        res = self.agent.agent_list_available_tools()
        self.assertIn("tools", res)
        tool_names = [t["name"] for t in res["tools"]]
        self.assertIn("get_date", tool_names)

        # Test model filter
        res_partner_tools = self.agent.agent_list_available_tools(
            res_model="res.partner"
        )
        partner_models = [t["model"] for t in res_partner_tools["tools"]]
        self.assertTrue(all(m == "res.partner" for m in partner_models))

    def test_agent_list_available_agents(self):
        res = self.agent.agent_list_available_agents()
        self.assertIn("agents", res)
        agent_names = [a["name"] for a in res["agents"]]
        self.assertIn("Tool Test Agent", agent_names)

    def test_agent_propose_action_plan(self):
        steps = [
            {
                "step_id": 1,
                "objective": "Check inventory",
                "target_type": "tool",
                "target_name": "get_date",
                "params": {},
                "depends_on": [],
            }
        ]
        res = self.agent.agent_propose_action_plan(summary="Test proposal", steps=steps)
        self.assertEqual(res["status"], "awaiting_approval")
        self.assertEqual(res["payload"]["summary"], "Test proposal")
        self.assertEqual(len(res["payload"]["steps"]), 1)
        self.assertEqual(res["payload"]["steps"][0]["objective"], "Check inventory")

        res_str = self.agent.agent_propose_action_plan(
            summary="JSON string steps", steps=json.dumps(steps)
        )
        self.assertEqual(res_str["status"], "awaiting_approval")
        self.assertEqual(len(res_str["payload"]["steps"]), 1)

        with self.assertRaises(ValidationError):
            self.agent.agent_propose_action_plan(
                summary="Bad steps", steps="<step>invalid</step>"
            )
