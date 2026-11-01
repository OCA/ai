# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests.common import TransactionCase


class TestAiToolSaleCrm(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stage = cls.env["crm.stage"].create({"name": "Qualified Stage"})
        cls.lead = cls.env["crm.lead"].create({"name": "Test CRM Lead"})

    def test_ai_update_lead_stage_succeeds(self):
        res = self.env["crm.lead"]._ai_update_lead_stage(
            lead_id=self.lead.id,
            stage_id=self.stage.id,
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["stage_name"], "Qualified Stage")
        self.assertEqual(self.lead.stage_id, self.stage)

    def test_ai_update_lead_stage_raises_value_error_for_invalid_lead(self):
        with self.assertRaises(ValueError):
            self.env["crm.lead"]._ai_update_lead_stage(
                lead_id=999999,
                stage_id=self.stage.id,
            )

    def test_ai_update_lead_stage_raises_value_error_for_invalid_stage(self):
        with self.assertRaises(ValueError):
            self.env["crm.lead"]._ai_update_lead_stage(
                lead_id=self.lead.id,
                stage_id=999999,
            )
