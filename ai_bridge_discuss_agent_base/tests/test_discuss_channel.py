from unittest.mock import patch

import markdown

from odoo.tests.common import TransactionCase

from odoo.addons.queue_job.tests.common import trap_jobs


class TestDiscussChannel(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.channel = cls.env["discuss.channel"].create(
            {
                "name": "Test Channel",
                "channel_type": "chat",
            }
        )
        cls.channel.channel_partner_ids = [(5, 0, 0)]  # Remove all default members

        cls.user = cls.env["res.users"].create(
            {
                "name": "Test User",
                "login": "test_user",
                "email": "test_user@example.com",
            }
        )
        cls.partner = cls.user.partner_id

        cls.ai_user = cls.env["res.users"].create(
            {
                "name": "AI Agent",
                "login": "ai_agent",
                "email": "ai_agent@example.com",
                "is_ai_agent": True,
                "custom_api_response_key": "response",
                "api_type": "custom_api",
                "api_endpoint": "http://mocked-ai-endpoint.com/respond",
                "api_timeout": 30,
                "auth_type": "none",
                "api_configuration_id": cls.env["agent.api.configuration"]
                .create(
                    {
                        "name": "Test AI Config",
                    }
                )
                .id,
            }
        )
        cls.ai_partner = cls.ai_user.partner_id

        cls.channel.channel_partner_ids = [(4, cls.partner.id), (4, cls.ai_partner.id)]

        admin_group = cls.env.ref("base.group_system")
        cls.ai_user.groups_id |= admin_group

    def test_message_post_non_ai_user(self):
        message = self.channel.message_post(
            body="Hello, this is a test message.",
            author_id=self.partner.id,
        )
        self.assertTrue(message, "Message should be posted successfully.")
        self.assertEqual(
            markdown.markdown(message.body), "<p>Hello, this is a test message.</p>"
        )
        self.assertEqual(message.author_id, self.partner)

    def test_message_post_ai_user(self):
        message = self.channel.message_post(
            body="AI-generated message.",
            author_id=self.ai_partner.id,
        )
        self.assertTrue(message, "Message should be posted successfully.")
        self.assertEqual(
            markdown.markdown(message.body), "<p>AI-generated message.</p>"
        )
        self.assertEqual(message.author_id, self.ai_partner)

    def test_message_post_empty_body(self):
        message = self.channel.message_post(
            body="",
            author_id=self.partner.id,
        )
        self.assertFalse(message.body, "Message body should be empty.")

    def test_message_post_with_context(self):
        context = {"agent_message": True}
        message = self.channel.with_context(**context).message_post(
            body="Message with custom context.",
            author_id=self.partner.id,
        )
        self.assertTrue(message, "Message should be posted successfully.")
        self.assertEqual(
            markdown.markdown(message.body), "<p>Message with custom context.</p>"
        )

    @patch("requests.post")
    def test_message_post_human_to_ai_response(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = [
            {"response": "This is an AI response."},
            {"response": "Another AI response."},
        ]
        with trap_jobs() as trap:
            message = self.channel.message_post(
                body="Hello AI, can you respond?",
                author_id=self.partner.id,
            )
            self.assertTrue(message, "Message should be posted successfully.")
            self.assertEqual(
                markdown.markdown(message.body), "<p>Hello AI, can you respond?</p>"
            )
            self.assertEqual(message.author_id, self.partner)
            enqueued_job = trap.enqueued_jobs[0]
            self.assertEqual(enqueued_job.func.__name__, "get_ai_agent_response_task")
            self.assertEqual(enqueued_job.args[0], message)
            self.assertEqual(enqueued_job.args[1], self.ai_user)
            trap.perform_enqueued_jobs()
            # perform again since the first one adds more jobs
            trap.perform_enqueued_jobs()

        ai_responses = self.channel.message_ids.filtered(
            lambda m: m.author_id == self.ai_partner
        )
        self.assertEqual(len(ai_responses), 2, "AI should have posted two responses.")
        ai_response_bodies = {
            markdown.markdown(response.body) for response in ai_responses
        }
        expected_responses = {
            "<p>This is an AI response.</p>",
            "<p>Another AI response.</p>",
        }
        self.assertSetEqual(
            ai_response_bodies,
            expected_responses,
            "AI responses do not match the expected responses.",
        )

    def test_no_jobs_with_agent_message_context(self):
        with trap_jobs() as trap:
            message = self.channel.with_context(agent_message=True).message_post(
                body="This is a message with agent_message=True context",
                author_id=self.partner.id,
            )
            self.assertTrue(message, "Message should be posted successfully")
            self.assertEqual(
                markdown.markdown(message.body),
                "<p>This is a message with agent_message=True context</p>",
            )
            self.assertEqual(
                len(trap.enqueued_jobs),
                0,
                "No jobs should be created when agent_message=True in context",
            )
