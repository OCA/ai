# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.tests.common import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestAsyncConnection(HttpCase):
    def setUp(self):
        super().setUp()
        self.bridge = self.env["ai.bridge"].create(
            {
                "name": "Test Bridge",
                "model_id": self.env.ref("base.model_res_partner").id,
                "url": "https://example.com/api",
                "auth_type": "none",
                "result_type": "message",
                "result_kind": "async",
                "usage": "thread",
            }
        )
        self.partner = self.env["res.partner"].create(
            {
                "name": "Test Partner",
                "email": "test@example.com",
            }
        )

        with mock.patch("requests.post") as mock_post:
            self.bridge.execute_ai_bridge(self.partner._name, self.partner.id)
            self.url = mock_post.call_args[1]["json"]["_response_url"]
        self.message_count = self.env["mail.message"].search_count(
            [
                ("model", "=", self.partner._name),
                ("res_id", "=", self.partner.id),
            ]
        )

    def test_connection(self):
        self.assertTrue(
            self.env["ai.bridge.execution"].search(
                [
                    ("ai_bridge_id", "=", self.bridge.id),
                    ("expiration_date", "!=", False),
                ]
            )
        )
        self.opener.post(self.url, json={"body": "Test response"})
        self.assertEqual(
            self.env["mail.message"].search_count(
                [
                    ("model", "=", self.partner._name),
                    ("res_id", "=", self.partner.id),
                ]
            ),
            self.message_count + 1,
            "A new message should be created in the thread.",
        )
        self.assertFalse(
            self.env["ai.bridge.execution"].search(
                [
                    ("ai_bridge_id", "=", self.bridge.id),
                    ("expiration_date", "!=", False),
                ]
            )
        )
