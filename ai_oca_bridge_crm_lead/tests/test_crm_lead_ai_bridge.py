# Copyright 2025 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.tests.common import TransactionCase


class TestCrmLeadAiBridge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.bridge_create = cls.env["ai.bridge"].create(
            {
                "name": "CRM Lead AI Bridge - Create",
                "description": "<p>Test bridge for CRM lead creation</p>",
                "model_id": cls.env.ref("crm.model_crm_lead").id,
                "usage": "ai_thread_create",
                "url": "https://api.example.com/ai/crm/create",
                "auth_type": "none",
                "payload_type": "record",
                "result_type": "none",
                "result_kind": "immediate",
                "field_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("crm.field_crm_lead__name").id,
                            cls.env.ref("crm.field_crm_lead__description").id,
                            cls.env.ref("crm.field_crm_lead__expected_revenue").id,
                        ],
                    )
                ],
            }
        )

        cls.bridge_write = cls.env["ai.bridge"].create(
            {
                "name": "CRM Lead AI Bridge - Update",
                "description": "<p>Test bridge for CRM lead updates</p>",
                "model_id": cls.env.ref("crm.model_crm_lead").id,
                "usage": "ai_thread_write",
                "url": "https://api.example.com/ai/crm/update",
                "auth_type": "none",
                "payload_type": "record",
                "result_type": "none",
                "result_kind": "immediate",
                "field_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("crm.field_crm_lead__name").id,
                            cls.env.ref("crm.field_crm_lead__description").id,
                            cls.env.ref("crm.field_crm_lead__expected_revenue").id,
                        ],
                    )
                ],
            }
        )

        cls.bridge_unlink = cls.env["ai.bridge"].create(
            {
                "name": "CRM Lead AI Bridge - Delete",
                "description": "<p>Test bridge for CRM lead deletion</p>",
                "model_id": cls.env.ref("crm.model_crm_lead").id,
                "usage": "ai_thread_unlink",
                "url": "https://api.example.com/ai/crm/delete",
                "auth_type": "none",
                "payload_type": "none",
                "result_type": "none",
                "result_kind": "immediate",
            }
        )

    def test_crm_lead_create_bridge(self):
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Lead created"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_create.id)]
                ),
            )
            lead = self.env["crm.lead"].create(
                {
                    "name": "Test Lead",
                    "description": "<p>This is a test lead for AI bridge</p>",
                    "expected_revenue": 1000.0,
                }
            )
            executions = self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge_create.id)]
            )
            self.assertEqual(len(executions), 1)
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "https://api.example.com/ai/crm/create")
            record = kwargs["json"].get("record", {})
            self.assertEqual(record.get("id"), lead.id)
            self.assertEqual(record.get("name"), "Test Lead")
            self.assertIn(
                "This is a test lead for AI bridge", record.get("description", "")
            )
            self.assertEqual(record.get("expected_revenue"), 1000.0)

    def test_crm_lead_write_bridge(self):
        self.bridge_create.active = False
        lead = self.env["crm.lead"].create(
            {
                "name": "Test Lead for Update",
                "description": "Initial description",
                "expected_revenue": 1000.0,
            }
        )
        self.bridge_create.active = True
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Lead updated"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_write.id)]
                ),
            )
            lead.write(
                {
                    "name": "Updated Lead",
                    "description": "<p>Updated description for AI bridge test</p>",
                    "expected_revenue": 2000.0,
                }
            )
            executions = self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge_write.id)]
            )
            self.assertEqual(len(executions), 1)
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "https://api.example.com/ai/crm/update")
            record = kwargs["json"].get("record", {})
            self.assertEqual(record.get("id"), lead.id)
            self.assertEqual(record.get("name"), "Updated Lead")
            self.assertIn(
                "Updated description for AI bridge test", record.get("description", "")
            )
            self.assertEqual(record.get("expected_revenue"), 2000.0)

    def test_crm_lead_unlink_bridge(self):
        self.bridge_create.active = False
        lead = self.env["crm.lead"].create(
            {
                "name": "Test Lead for Deletion",
                "description": "<p>Description to be deleted</p>",
                "expected_revenue": 1500.0,
            }
        )
        self.bridge_create.active = True
        lead_id = lead.id
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Lead deleted"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_unlink.id)]
                ),
            )
            lead.unlink()
            executions = self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge_unlink.id)]
            )
            self.assertEqual(len(executions), 1)
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "https://api.example.com/ai/crm/delete")
            self.assertEqual(kwargs["json"].get("_id", False), lead_id)

    def test_all_bridges_together(self):
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Success"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_create.id)]
                ),
            )
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_write.id)]
                ),
            )
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_unlink.id)]
                ),
            )
            lead = self.env["crm.lead"].create(
                {
                    "name": "Complete Test Lead",
                    "description": "Initial description for complete test",
                    "expected_revenue": 2500.0,
                }
            )
            lead.write(
                {
                    "description": "Updated description for complete test",
                    "expected_revenue": 3000.0,
                }
            )
            lead.unlink()

            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_create.id)]
                ),
            )
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_write.id)]
                ),
            )
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_unlink.id)]
                ),
            )
