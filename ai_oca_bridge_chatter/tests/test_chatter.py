# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.tests import common, new_test_user


class TestChatter(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, mail_create_nosubscribe=True))
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "Test Bridge",
                "model_id": cls.env.ref("base.model_res_partner").id,
                "url": "https://example.com/api",
                "auth_type": "none",
                "usage": "chatter",
                "payload_type": "chatter",
                "result_kind": "immediate",
                # We will use the immediate result_kind to simplify the test
                "result_type": "message",
            }
        )
        cls.ai_user = new_test_user(
            cls.env,
            login="test-chatter-user",
            groups="base.group_user",
        )
        cls.ai_user.write({"ai_bridge_id": cls.bridge.id})
        cls.user = new_test_user(
            cls.env,
            login="test-chatter-user-2",
            groups="base.group_user",
        )
        cls.chat = (
            cls.env["mail.channel"]
            .with_user(cls.user.id)
            .create(
                {
                    "name": "Test Channel",
                    "channel_type": "chat",
                    "channel_member_ids": [
                        (0, 0, {"partner_id": cls.ai_user.partner_id.id}),
                        (0, 0, {"partner_id": cls.user.partner_id.id}),
                    ],
                }
            )
        )
        cls.channel = cls.env["mail.channel"].create(
            {
                "name": "Main Channel",
                "channel_type": "channel",
                "channel_member_ids": [
                    (0, 0, {"partner_id": cls.ai_user.partner_id.id}),
                    (0, 0, {"partner_id": cls.user.partner_id.id}),
                    (0, 0, {"partner_id": cls.env.user.partner_id.id}),
                ],
            }
        )

    def test_user_status(self):
        self.assertEqual("online", self.ai_user.partner_id.im_status)
        self.assertEqual("offline", self.user.partner_id.im_status)
        self.assertEqual("online", self.ai_user.im_status)
        self.assertEqual("offline", self.user.im_status)

    def test_chat(self):
        """Answer is direct in this case"""
        self.assertFalse(
            self.env["mail.message"].search(
                [("res_id", "=", self.chat.id), ("model", "=", "mail.channel")]
            ),
        )
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = mock.Mock(
                status_code=200, json=lambda: {"body": "My message"}
            )
            self.chat.with_user(self.user.id).message_post(
                body="Test message",
            )
            mock_post.assert_called_once()
        self.assertEqual(
            2,
            self.env["mail.message"].search_count(
                [("res_id", "=", self.chat.id), ("model", "=", "mail.channel")]
            ),
        )

    def test_channel_not_called(self):
        """No AI bridge should be called when the user is not callend in the channel"""
        self.assertFalse(
            self.env["mail.message"].search(
                [("res_id", "=", self.channel.id), ("model", "=", "mail.channel")]
            ),
        )
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = mock.Mock(
                status_code=200, json=lambda: {"body": "My message"}
            )
            self.channel.with_user(self.user.id).message_post(
                body="Test message",
            )
            mock_post.assert_not_called()
        self.assertEqual(
            1,
            self.env["mail.message"].search_count(
                [("res_id", "=", self.channel.id), ("model", "=", "mail.channel")]
            ),
        )

    def test_channel_called(self):
        """Test that AI answers only if they are called in channels"""
        self.assertFalse(
            self.env["mail.message"].search(
                [("res_id", "=", self.channel.id), ("model", "=", "mail.channel")]
            ),
        )
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = mock.Mock(
                status_code=200, json=lambda: {"body": "My message"}
            )
            self.channel.with_user(self.user.id).message_post(
                body="Test message",
                partner_ids=[self.ai_user.partner_id.id],
            )
            mock_post.assert_called_once()
        self.assertEqual(
            2,
            self.env["mail.message"].search_count(
                [("res_id", "=", self.channel.id), ("model", "=", "mail.channel")]
            ),
        )

    def test_channel_multiple_calls(self):
        """Test that AI answers might be from multiple users in the channel at the same time"""
        self.assertFalse(
            self.env["mail.message"].search(
                [("res_id", "=", self.channel.id), ("model", "=", "mail.channel")]
            ),
        )
        self.user.ai_bridge_id = self.bridge
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = mock.Mock(
                status_code=200, json=lambda: {"body": "My message"}
            )
            self.channel.message_post(
                body="Test message",
                partner_ids=[self.ai_user.partner_id.id, self.user.partner_id.id],
            )
            mock_post.assert_called()
        self.assertEqual(
            3,
            self.env["mail.message"].search_count(
                [("res_id", "=", self.channel.id), ("model", "=", "mail.channel")]
            ),
        )

    def test_chat_ai_no_answer(self):
        """Test that AI does not answer to AI messages"""
        self.assertFalse(
            self.env["mail.message"].search(
                [("res_id", "=", self.channel.id), ("model", "=", "mail.channel")]
            ),
        )
        self.user.ai_bridge_id = self.bridge
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = mock.Mock(
                status_code=200, json=lambda: {"body": "My message"}
            )
            self.channel.with_user(self.user.id).message_post(
                body="Test message",
                partner_ids=[self.ai_user.partner_id.id],
            )
            mock_post.assert_not_called()
        self.assertEqual(
            1,
            self.env["mail.message"].search_count(
                [("res_id", "=", self.channel.id), ("model", "=", "mail.channel")]
            ),
        )
