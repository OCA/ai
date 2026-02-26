from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestAiThread(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Test Context Partner"})
        cls.thread = cls.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": cls.partner.id,
            }
        )

    def test_default_name(self):
        self.assertEqual(
            self.thread.name,
            "New Thread",
        )

    def test_action_send_message_success(self):
        # Standard Odoo method to mock methods on models
        with patch.object(
            type(self.env["ai.llm.client"]),
            "chat",
            side_effect=["Mock Title", "Hello from AI", "An other response"],
        ) as mock_chat:
            res = self.thread.action_send_message("Hi AI")

            # Check response
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["content"], "Hello from AI")
            self.assertIn("Mock Title", res["thread_name"])

            # Check messages created
            messages = self.thread.message_ids.sorted("create_date")
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[0].role, "user")
            self.assertEqual(messages[0].content, "Hi AI")
            self.assertEqual(messages[1].role, "assistant")
            self.assertEqual(messages[1].content, "Hello from AI")

            # Check arguments passed to chat
            call_args = mock_chat.call_args_list[-1][0][0]
            self.assertTrue(len(call_args) >= 2)
            self.assertEqual(call_args[0]["role"], "system")
            self.assertIn("Test Context Partner", call_args[0]["content"])
            self.assertEqual(call_args[-1]["role"], "user")
            self.assertEqual(call_args[-1]["content"], "Hi AI")

            # Cover some missed branch when it's not the
            # first message of the thread
            with patch.object(
                type(self.env["ai.thread"]), "_get_record_context", return_value={}
            ):
                res = self.thread.action_send_message("Hi Again")
                messages = self.thread.message_ids.sorted("create_date")
                self.assertEqual(len(messages), 4)
                self.assertEqual(messages[2].role, "user")
                self.assertEqual(messages[2].content, "Hi Again")
                self.assertEqual(messages[3].role, "assistant")
                self.assertEqual(messages[3].content, "An other response")

    def test_action_send_message_empty_response(self):
        thread2 = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
            }
        )
        with patch.object(type(self.env["ai.llm.client"]), "chat", return_value=""):
            res = thread2.action_send_message("Hi again")

            self.assertEqual(
                res, {"status": "error", "content": "No response from LLM"}
            )

            # Check message created (only user message)
            messages = thread2.message_ids.sorted("create_date")
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0].role, "user")
            self.assertEqual(messages[0].content, "Hi again")

    def test_action_send_message_no_record(self):
        thread3 = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": 999999,
            }
        )
        with patch.object(
            type(self.env["ai.llm.client"]), "chat", return_value="Hello"
        ) as mock_chat:
            res = thread3.action_send_message("Testing missing record")
            self.assertEqual(res["status"], "success")
            # When record doesn't exist, it shouldn't inject display_name
            call_args = mock_chat.call_args_list[-1][0][0]
            self.assertNotIn("The contextual record name is", call_args[0]["content"])
