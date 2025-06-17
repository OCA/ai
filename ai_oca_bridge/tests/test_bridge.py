# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
from unittest import mock

from odoo.tests.common import TransactionCase


class TestBridge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "Test Bridge",
                "model_id": cls.env.ref("base.model_res_partner").id,
                "url": "https://example.com/api",
                "auth_type": "none",
                "usage": "thread",
            }
        )
        # We add this in order to simplify tests, as jsons will be filled.
        cls.bridge_extra = cls.env["ai.bridge"].create(
            {
                "name": "Test Bridge Extra",
                "model_id": cls.env.ref("base.model_res_partner").id,
                "url": "https://example.com/api",
                "auth_type": "none",
                "usage": "thread",
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Test Partner",
                "email": "test@example.com",
            }
        )
        cls.group = cls.env["res.groups"].create(
            {
                "name": "Test Group",
            }
        )

    def test_bridge_none_auth(self):
        self.assertEqual(self.bridge.auth_type, "none")
        self.assertTrue(self.partner.ai_bridge_info)
        self.assertIn(
            self.bridge.id, [bridge["id"] for bridge in self.partner.ai_bridge_info]
        )
        self.assertFalse(
            self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge.id)]
            )
        )
        with mock.patch("requests.post") as mock_post:
            self.bridge.execute_ai_bridge(self.partner._name, self.partner.id)
            mock_post.assert_called_once()
        self.assertTrue(
            self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge.id)]
            )
        )
        execution = self.env["ai.bridge.execution"].search(
            [("ai_bridge_id", "=", self.bridge.id)]
        )
        self.assertEqual(execution.res_id, self.partner.id)
        self.assertNotIn("name", execution.payload)

    def test_bridge_none_auth_fields_record_v0(self):
        self.bridge.write(
            {
                "payload_type": "record_v0",
                "auth_type": "none",
                "field_ids": [
                    (4, self.env.ref("base.field_res_partner__name").id),
                    (4, self.env.ref("base.field_res_partner__create_date").id),
                    (4, self.env.ref("base.field_res_partner__image_1920").id),
                ],
            }
        )
        self.assertTrue(self.partner.ai_bridge_info)
        self.assertIn(
            self.bridge.id, [bridge["id"] for bridge in self.partner.ai_bridge_info]
        )
        self.assertFalse(
            self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge.id)]
            )
        )
        with mock.patch("requests.post") as mock_post:
            self.bridge.execute_ai_bridge(self.partner._name, self.partner.id)
            mock_post.assert_called_once()
        self.assertTrue(
            self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge.id)]
            )
        )
        execution = self.env["ai.bridge.execution"].search(
            [("ai_bridge_id", "=", self.bridge.id)]
        )
        self.assertEqual(execution.res_id, self.partner.id)
        self.assertIn("name", execution.payload)
        self.assertEqual(execution.payload["name"], self.partner.name)
        self.assertEqual(1, self.bridge.execution_count)

    def test_bridge_none_auth_fields_record(self):
        self.bridge.write(
            {
                "payload_type": "record",
                "auth_type": "none",
                "field_ids": [
                    (4, self.env.ref("base.field_res_partner__name").id),
                    (4, self.env.ref("base.field_res_partner__create_date").id),
                    (4, self.env.ref("base.field_res_partner__image_1920").id),
                ],
            }
        )
        self.assertTrue(self.partner.ai_bridge_info)
        self.assertIn(
            self.bridge.id, [bridge["id"] for bridge in self.partner.ai_bridge_info]
        )
        self.assertFalse(
            self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge.id)]
            )
        )
        with mock.patch("requests.post") as mock_post:
            self.bridge.execute_ai_bridge(self.partner._name, self.partner.id)
            mock_post.assert_called_once()
        self.assertTrue(
            self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge.id)]
            )
        )
        execution = self.env["ai.bridge.execution"].search(
            [("ai_bridge_id", "=", self.bridge.id)]
        )
        self.assertEqual(execution.res_id, self.partner.id)
        self.assertIn("name", execution.payload["record"])
        self.assertEqual(execution.payload["record"]["name"], self.partner.name)
        self.assertEqual(1, self.bridge.execution_count)

    def test_bridge_basic_auth(self):
        self.bridge.write(
            {
                "auth_type": "basic",
                "auth_username": "test_user",
                "auth_password": "test_pass",
            }
        )
        self.assertTrue(self.partner.ai_bridge_info)
        self.assertIn(
            self.bridge.id, [bridge["id"] for bridge in self.partner.ai_bridge_info]
        )
        self.assertFalse(
            self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge.id)]
            )
        )
        with mock.patch("requests.post") as mock_post:
            self.bridge.execute_ai_bridge(self.partner._name, self.partner.id)
            mock_post.assert_called_once()
        self.assertTrue(
            self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge.id)]
            )
        )

    def test_bridge_token_auth(self):
        self.bridge.write(
            {
                "auth_type": "token",
                "auth_token": "test_token",
            }
        )
        self.assertTrue(self.partner.ai_bridge_info)
        self.assertIn(
            self.bridge.id, [bridge["id"] for bridge in self.partner.ai_bridge_info]
        )
        self.assertFalse(
            self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge.id)]
            )
        )
        with mock.patch("requests.post") as mock_post:
            self.bridge.execute_ai_bridge(self.partner._name, self.partner.id)
            mock_post.assert_called_once()
        self.assertTrue(
            self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge.id)]
            )
        )

    def test_bridge_error(self):
        self.assertTrue(self.partner.ai_bridge_info)
        self.assertIn(
            self.bridge.id, [bridge["id"] for bridge in self.partner.ai_bridge_info]
        )
        self.assertFalse(
            self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge.id)]
            )
        )
        self.bridge.execute_ai_bridge(self.partner._name, self.partner.id)
        execution = self.env["ai.bridge.execution"].search(
            [("ai_bridge_id", "=", self.bridge.id)]
        )
        self.assertTrue(execution)
        self.assertTrue(execution.error)

    def test_bridge_unactive(self):
        self.bridge.toggle_active()
        self.assertFalse(
            self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge.id)]
            )
        )
        self.bridge.execute_ai_bridge(self.partner._name, self.partner.id)
        execution = self.env["ai.bridge.execution"].search(
            [("ai_bridge_id", "=", self.bridge.id)]
        )
        self.assertFalse(execution)

    def test_bridge_check_group(self):
        self.bridge.group_ids = [(4, self.group.id)]
        self.assertFalse(
            self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge.id)]
            )
        )
        self.bridge.execute_ai_bridge(self.partner._name, self.partner.id)
        execution = self.env["ai.bridge.execution"].search(
            [("ai_bridge_id", "=", self.bridge.id)]
        )
        self.assertFalse(execution)

    def test_bridge_domain_filtering(self):
        self.assertTrue(self.partner.ai_bridge_info)
        self.assertIn(
            self.bridge.id, [bridge["id"] for bridge in self.partner.ai_bridge_info]
        )
        self.bridge.write({"domain": f"[('id', '!=', {self.partner.id})]"})
        self.partner.invalidate_recordset()
        self.assertNotIn(
            self.bridge.id, [bridge["id"] for bridge in self.partner.ai_bridge_info]
        )

    def test_bridge_group_filtering(self):
        self.assertTrue(self.partner.ai_bridge_info)
        self.assertIn(
            self.bridge.id, [bridge["id"] for bridge in self.partner.ai_bridge_info]
        )
        self.bridge.write({"group_ids": [(4, self.group.id)]})
        self.partner.invalidate_recordset()
        self.assertNotIn(
            self.bridge.id, [bridge["id"] for bridge in self.partner.ai_bridge_info]
        )
        self.env.user.groups_id |= self.group
        self.partner.invalidate_recordset()
        self.assertIn(
            self.bridge.id, [bridge["id"] for bridge in self.partner.ai_bridge_info]
        )

    def test_view_fields(self):
        view = self.partner.get_view(view_type="form")
        self.assertIn("ai_bridge_info", view["models"][self.partner._name])
        self.assertIn(b'name="ai_bridge_info"', view["arch"])

    def test_sample(self):
        self.assertTrue(self.bridge.sample_payload)
        self.assertIn("_id", self.bridge.sample_payload)

    def test_bridge_result_message(self):
        self.bridge.write({"result_type": "message"})
        self.assertFalse(
            self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge.id)]
            )
        )
        message_count = self.env["mail.message"].search_count(
            [("model", "=", self.partner._name), ("res_id", "=", self.partner.id)]
        )
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = mock.Mock(
                status_code=200, json=lambda: {"body": "My message"}
            )
            self.bridge.execute_ai_bridge(self.partner._name, self.partner.id)
            mock_post.assert_called_once()
        self.assertEqual(
            self.env["mail.message"].search_count(
                [("model", "=", self.partner._name), ("res_id", "=", self.partner.id)]
            ),
            message_count + 1,
        )

    def test_bridge_result_message_async(self):
        self.bridge.write({"result_type": "message", "result_kind": "async"})
        self.assertFalse(
            self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge.id)]
            )
        )
        message_count = self.env["mail.message"].search_count(
            [("model", "=", self.partner._name), ("res_id", "=", self.partner.id)]
        )
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = mock.Mock(
                status_code=200, json=lambda: {"body": "My message"}
            )
            self.bridge.execute_ai_bridge(self.partner._name, self.partner.id)
            mock_post.assert_called_once()
        self.assertEqual(
            self.env["mail.message"].search_count(
                [("model", "=", self.partner._name), ("res_id", "=", self.partner.id)]
            ),
            message_count,
        )
        execution = self.env["ai.bridge.execution"].search(
            [("ai_bridge_id", "=", self.bridge.id)]
        )
        self.assertTrue(execution.expiration_date)
        execution._process_response({"body": "My message"})
        self.assertEqual(
            self.env["mail.message"].search_count(
                [("model", "=", self.partner._name), ("res_id", "=", self.partner.id)]
            ),
            message_count + 1,
        )
        self.assertFalse(execution.expiration_date)

    def test_bridge_result_action_immediate(self):
        self.bridge.write({"result_type": "action", "result_kind": "immediate"})
        self.assertFalse(
            self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge.id)]
            )
        )
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = mock.Mock(
                status_code=200,
                json=lambda: {
                    "action": "ai_oca_bridge.ai_bridge_act_window",
                    "context": {"key": "value"},
                },
            )
            result = self.bridge.execute_ai_bridge(self.partner._name, self.partner.id)
            mock_post.assert_called_once()
        self.assertIn("action", result)
        self.assertEqual(
            result["action"]["id"],
            self.env.ref("ai_oca_bridge.ai_bridge_act_window").id,
        )

    def test_bridge_execute_computed_fields(self):
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = mock.Mock(
                status_code=200, json=lambda: {"body": "My message"}
            )
            self.bridge.execute_ai_bridge(self.partner._name, self.partner.id)
            mock_post.assert_called_once()
        execution = self.env["ai.bridge.execution"].search(
            [("ai_bridge_id", "=", self.bridge.id)]
        )
        self.assertEqual(
            execution.payload["_id"], json.loads(execution.payload_txt)["_id"]
        )
