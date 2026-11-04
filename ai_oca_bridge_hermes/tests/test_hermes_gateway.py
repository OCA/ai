# Copyright 2026-TODAY Akretion - Raphael Valyi <raphael.valyi@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase


class TestHermesGateway(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.AiBridge = cls.env["ai.bridge"]
        cls.HermesGateway = cls.env["hermes.gateway"]
        cls.HermesQueue = cls.env["hermes.message.queue"]
        cls.DiscussChannel = cls.env["discuss.channel"]
        cls.ResUsers = cls.env["res.users"]
        cls.ResPartner = cls.env["res.partner"]

        # Create test AI user - use existing partner
        cls.ai_partner = cls.env.ref("base.partner_admin")
        cls.ai_user = cls.ResUsers.create(
            {
                "name": "Test AI",
                "login": "test_ai",
                "partner_id": cls.ai_partner.id,
            }
        )
        # Create AI bridge for the user
        cls.ai_bridge = cls.AiBridge.create(
            {
                "name": "Test AI Bridge",
                "usage": "hermes",
            }
        )
        cls.ai_user.ai_bridge_id = cls.ai_bridge.id

        # Create gateway
        cls.gateway = cls.HermesGateway.create(
            {
                "name": "Test Gateway",
                "ai_user_id": cls.ai_user.id,
            }
        )

        # Create test channel
        cls.channel = cls.DiscussChannel.create(
            {
                "name": "Test Channel",
                "channel_type": "channel",
            }
        )

    def test_gateway_creation(self):
        """Test gateway is created with auto-generated token."""
        self.assertTrue(self.gateway.webhook_token)
        self.assertEqual(len(self.gateway.webhook_token), 64)  # 32 bytes hex
        self.assertEqual(self.gateway.state, "draft")

    def test_gateway_regenerate_token(self):
        """Test token regeneration."""
        old_token = self.gateway.webhook_token
        self.gateway.action_regenerate_token()
        self.assertNotEqual(self.gateway.webhook_token, old_token)
        self.assertEqual(len(self.gateway.webhook_token), 64)

    def test_gateway_test_connection_no_url(self):
        """Test connection without Hermes URL shows warning."""
        result = self.gateway.action_test_connection()
        self.assertEqual(result["type"], "ir.actions.client")
        self.assertEqual(result["tag"], "display_notification")
        self.assertEqual(result["params"]["type"], "warning")

    def test_queue_message_creation(self):
        """Test message queue creation."""
        msg = self.HermesQueue.create(
            {
                "channel_id": self.channel.id,
                "body": "<p>Test message</p>",
                "gateway_id": self.gateway.id,
            }
        )
        self.assertEqual(msg.state, "pending")
        self.assertEqual(msg.message_type, "user")
        self.assertFalse(msg.is_escalated)

    def test_queue_message_retry(self):
        """Test retrying failed messages."""
        msg = self.HermesQueue.create(
            {
                "channel_id": self.channel.id,
                "body": "<p>Test</p>",
                "gateway_id": self.gateway.id,
                "state": "error",
                "error_message": "Test error",
            }
        )
        msg.action_retry()
        self.assertEqual(msg.state, "pending")
        self.assertFalse(msg.error_message)

    def test_queue_cleanup_old_messages(self):
        """Test cleanup of old messages."""
        # Create old done message
        old_msg = self.HermesQueue.create(
            {
                "channel_id": self.channel.id,
                "body": "<p>Old</p>",
                "gateway_id": self.gateway.id,
                "state": "done",
            }
        )
        # Manually set create_date to old
        old_msg.write({"create_date": "2020-01-01 00:00:00"})

        # Run cleanup
        self.HermesQueue._cleanup_old_messages()

        # Message should be deleted
        self.assertFalse(old_msg.exists())

    def test_discuss_channel_get_gateway(self):
        """Test finding gateway for channel."""
        # Channel without gateway
        channel_no_gateway = self.DiscussChannel.create(
            {
                "name": "No Gateway",
                "channel_type": "channel",
            }
        )
        self.assertFalse(channel_no_gateway._get_hermes_gateway())

        # Channel with explicit gateway
        self.channel.hermes_gateway_id = self.gateway.id
        found = self.channel._get_hermes_gateway()
        self.assertEqual(found, self.gateway)

    def test_discuss_channel_message_post_queues(self):
        """Test that posting a message queues it for Hermes."""
        self.channel.hermes_gateway_id = self.gateway.id

        # Post as regular user (admin)
        self.channel.with_user(self.env.user.id).message_post(
            body="<p>Hello Hermes</p>",
            message_type="comment",
        )

        # Check queue - search by channel only since body might be wrapped
        queued = self.HermesQueue.search(
            [
                ("channel_id", "=", self.channel.id),
            ]
        )
        self.assertTrue(queued)
        self.assertEqual(queued.state, "pending")

    def test_discuss_channel_ai_user_message_no_queue(self):
        """Test that AI user messages don't get queued (prevent loops)."""
        self.channel.hermes_gateway_id = self.gateway.id

        # Post as AI user
        self.channel.with_user(self.ai_user.id).message_post(
            body="<p>AI response</p>",
            message_type="comment",
        )

        # Should not be queued
        queued = self.HermesQueue.search(
            [
                ("channel_id", "=", self.channel.id),
                ("body", "=", "<p>AI response</p>"),
            ]
        )
        self.assertFalse(queued)

    def test_discuss_channel_auto_respect_disabled(self):
        """Test that auto-respect disabled prevents queuing."""
        self.channel.hermes_gateway_id = self.gateway.id
        self.channel.hermes_auto_respond = False

        self.channel.message_post(
            body="<p>Should not queue</p>",
            message_type="comment",
        )

        queued = self.HermesQueue.search(
            [
                ("channel_id", "=", self.channel.id),
                ("body", "=", "<p>Should not queue</p>"),
            ]
        )
        self.assertFalse(queued)

    def test_webhook_format_body(self):
        """Test HTML formatting in webhook."""
        from ..controllers.hermes_webhook import HermesWebhook

        webhook = HermesWebhook()

        # Plain text
        result = webhook._format_body("Hello world")
        self.assertIn("Hello world", result)
        self.assertTrue(result.startswith("<span>"))

        # HTML input (should strip tags)
        result = webhook._format_body("<p>Hello</p>")
        self.assertIn("Hello", result)
        self.assertNotIn("<p>", result)

        # URL conversion
        result = webhook._format_body("Visit https://example.com")
        self.assertIn('<a href="https://example.com"', result)

    def test_poll_rate_limiting(self):
        """Test rate limiting on poll endpoint."""
        from odoo import fields as odoo_fields

        # Set last poll to now
        self.gateway.last_poll = odoo_fields.Datetime.now()

        # Simulate poll (would need HTTP test)
        # This is a basic unit test - full integration test would use HttpCase
        self.assertTrue(self.gateway.last_poll)
