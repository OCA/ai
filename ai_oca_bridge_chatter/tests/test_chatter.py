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
            cls.env["discuss.channel"]
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
        cls.channel = cls.env["discuss.channel"].create(
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
                [("res_id", "=", self.chat.id), ("model", "=", "discuss.channel")]
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
                [("res_id", "=", self.chat.id), ("model", "=", "discuss.channel")]
            ),
        )

    def test_channel_not_called(self):
        """No AI bridge should be called when the user is not callend in the channel"""
        self.assertFalse(
            self.env["mail.message"].search(
                [("res_id", "=", self.channel.id), ("model", "=", "discuss.channel")]
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
                [("res_id", "=", self.channel.id), ("model", "=", "discuss.channel")]
            ),
        )

    def test_channel_called(self):
        """Test that AI answers only if they are called in channels"""
        self.assertFalse(
            self.env["mail.message"].search(
                [("res_id", "=", self.channel.id), ("model", "=", "discuss.channel")]
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
                [("res_id", "=", self.channel.id), ("model", "=", "discuss.channel")]
            ),
        )

    def test_channel_multiple_calls(self):
        """Test that AI answers might be from multiple users
        in the channel at the same time"""
        self.assertFalse(
            self.env["mail.message"].search(
                [("res_id", "=", self.channel.id), ("model", "=", "discuss.channel")]
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
                [("res_id", "=", self.channel.id), ("model", "=", "discuss.channel")]
            ),
        )

    def test_chat_ai_no_answer(self):
        """Test that AI does not answer to AI messages"""
        self.assertFalse(
            self.env["mail.message"].search(
                [("res_id", "=", self.channel.id), ("model", "=", "discuss.channel")]
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
                [("res_id", "=", self.channel.id), ("model", "=", "discuss.channel")]
            ),
        )

    def test_prepare_payload_without_parent(self):
        """A standalone message exposes parent as False."""
        message = self.channel.with_user(self.user.id).message_post(
            body="Standalone message",
        )
        payload = self.bridge._prepare_payload_chatter(record=message)
        self.assertFalse(payload["message"]["parent_id"])
        self.assertFalse(payload["message"]["parent"])

    def test_prepare_payload_with_parent(self):
        """A reply includes the quoted parent body and author."""
        parent = self.channel.message_post(
            body="<p>Architect proposal</p>",
            author_id=self.ai_user.partner_id.id,
        )
        reply = self.channel.with_user(self.user.id).message_post(
            body="Please evaluate",
            parent_id=parent.id,
        )
        payload = self.bridge._prepare_payload_chatter(record=reply)
        self.assertEqual(payload["message"]["parent_id"], parent.id)
        self.assertEqual(payload["message"]["parent"]["id"], parent.id)
        self.assertIn("Architect proposal", payload["message"]["parent"]["body"])
        self.assertEqual(
            payload["message"]["parent"]["author_name"],
            self.ai_user.partner_id.name,
        )
        self.assertEqual(
            payload["message"]["parent"]["author_id"],
            self.ai_user.partner_id.id,
        )
        self.assertTrue(payload["message"]["parent"]["date"])

    def test_channel_reply_sends_parent(self):
        """Mentioning a bot in a reply posts the quoted message to the bridge."""
        parent = self.channel.message_post(
            body="<p>Architect proposal</p>",
            author_id=self.ai_user.partner_id.id,
        )
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value = mock.Mock(
                status_code=200, json=lambda: {"body": "My review"}
            )
            self.channel.with_user(self.user.id).message_post(
                body="Please evaluate",
                parent_id=parent.id,
                partner_ids=[self.ai_user.partner_id.id],
            )
            mock_post.assert_called_once()
        sent = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get(
            "json"
        )
        self.assertIn("Architect proposal", sent["message"]["parent"]["body"])
        self.assertEqual(sent["message"]["parent"]["id"], parent.id)
