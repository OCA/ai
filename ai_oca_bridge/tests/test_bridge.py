# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

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

    def test_bridge_none_auth_fields(self):
        self.bridge.write(
            {
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
