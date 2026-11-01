# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests.common import TransactionCase


class TestAiAgentSalesman(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sales_agent = cls.env.ref("ai_agent_salesman.agent_salesman")
        cls.stage_new = cls.env["crm.stage"].create({"name": "New Opportunity"})
        cls.stage_won = cls.env["crm.stage"].create({"name": "Won Opportunity"})
        cls.lead = cls.env["crm.lead"].create(
            {
                "name": "Test Prospect Deal",
                "stage_id": cls.stage_new.id,
                "user_id": cls.sales_agent.user_id.id,
            }
        )

    def test_salesman_agent_configuration_and_persona(self):
        self.assertEqual(self.sales_agent.execution_mode, "dedicated_agent")
        self.assertTrue(self.sales_agent.user_id.is_ai_agent)
        self.assertEqual(self.sales_agent.persona_id.code, "sales_specialist")
        rendered_prompt = self.sales_agent.persona_id.system_prompt_id.render()
        self.assertIn("dedicated Odoo Sales AI Agent", rendered_prompt)

    def test_salesman_agent_tools_definition_export(self):
        definitions = self.sales_agent.get_tools_definitions()
        names = [d["name"] for d in definitions]
        self.assertIn("update_lead_stage", names)
        self.assertIn("get_date", names)

    def test_salesman_agent_executes_update_lead_stage_tool(self):
        res = self.sales_agent.execute_tool(
            "update_lead_stage",
            params={
                "lead_id": self.lead.id,
                "stage_id": self.stage_won.id,
            },
        )
        self.assertTrue(res.get("success"))
        self.assertEqual(res.get("stage_name"), "Won Opportunity")
        self.assertEqual(self.lead.stage_id, self.stage_won)
