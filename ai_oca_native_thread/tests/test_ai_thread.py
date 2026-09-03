from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase

from odoo.addons.queue_job.tests.common import trap_jobs


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

    def test_record_property(self):
        self.assertEqual(self.thread.record, self.partner)

        thread_nonexistent = self.env["ai.thread"].new(
            {
                "res_model": "res.partner",
                "res_id": 999999,
            }
        )
        self.assertIsNone(thread_nonexistent.record)

        thread_invalid_model = self.env["ai.thread"].new(
            {
                "res_model": "non.existent.model",
                "res_id": 1,
            }
        )
        self.assertIsNone(thread_invalid_model.record)

        thread_empty = self.env["ai.thread"].new({})
        self.assertIsNone(thread_empty.record)

    def test_action_send_message_success(self):
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
            }
        )

        def mock_chat_side_effect(messages, **kwargs):
            content = messages[-1]["content"] if messages else ""
            if "title" in content.lower():
                return "Hi AI"
            return "Hello from AI"

        with (
            trap_jobs() as trap,
            patch.object(
                type(self.env["ai.llm.client"]),
                "chat",
                side_effect=mock_chat_side_effect,
            ),
        ):
            res = thread.action_send_message("Hi AI")

            self.assertEqual(res["status"], "pending")
            self.assertEqual(res["thread_name"], "Hi AI")

            messages = thread.message_ids.sorted("create_date")
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[0].role, "user")
            self.assertEqual(messages[0].content, "Hi AI")
            self.assertEqual(messages[1].role, "assistant")
            self.assertEqual(messages[1].status, "processing")

            trap.assert_jobs_count(1, only=messages[1]._action_extract_intent)
            trap.assert_enqueued_job(
                messages[1]._action_extract_intent,
                args=(),
                kwargs={},
                properties=dict(channel=messages[1].queue_job_channel_name),
            )

            with patch.object(type(self.env["bus.bus"]), "_sendone") as mock_sendone:
                trap.perform_enqueued_jobs()
                mock_sendone.assert_called_once()

            thread = self.env["ai.thread"].browse(thread.id)
            self.assertEqual(thread.name, "Hi AI")

            messages = thread.message_ids.sorted("create_date")
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[1].role, "assistant")
            self.assertEqual(messages[1].content, "Hello from AI")
            self.assertEqual(messages[1].status, "done")

    def test_extract_intent_cancelled_message(self):
        msg = self.env["ai.message"].create(
            {
                "thread_id": self.thread.id,
                "role": "assistant",
                "status": "cancel",
                "content": "",
            }
        )
        # Should return early
        msg._action_extract_intent()
        self.assertEqual(msg.content, "")

    def test_extract_intent_success(self):
        msg = self.env["ai.message"].create(
            {
                "thread_id": self.thread.id,
                "role": "assistant",
                "status": "processing",
                "content": "",
            }
        )
        with patch.object(
            type(self.env["ai.llm.client"]),
            "chat",
            return_value="Direct assistant completion.",
        ):
            msg._action_extract_intent()
        self.assertEqual(msg.status, "done")
        self.assertEqual(msg.content, "Direct assistant completion.")

    def test_extract_intent_empty_llm_response(self):
        msg = self.env["ai.message"].create(
            {
                "thread_id": self.thread.id,
                "role": "assistant",
                "status": "processing",
                "content": "",
            }
        )
        with patch.object(
            type(self.env["ai.llm.client"]),
            "chat",
            return_value=None,
        ):
            msg._action_extract_intent()
        self.assertEqual(msg.status, "cancel")
        self.assertEqual(msg.content, "Failed to get a response from LLM.")

    def test_action_send_message_empty_response(self):
        thread2 = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
            }
        )
        with trap_jobs() as trap:
            with patch.object(type(self.env["ai.llm.client"]), "chat", return_value=""):
                res = thread2.action_send_message("Hi again")
                self.assertEqual(res["status"], "pending")
                self.assertEqual(res["thread_name"], "Hi again")

                trap.assert_jobs_count(1)

                with patch.object(type(self.env["bus.bus"]), "_sendone"):
                    trap.perform_enqueued_jobs()

                messages = thread2.message_ids.sorted("create_date")
                self.assertEqual(len(messages), 2)
                self.assertEqual(messages[0].role, "user")
                self.assertEqual(messages[0].content, "Hi again")
                self.assertEqual(messages[1].role, "assistant")
                self.assertEqual(messages[1].status, "cancel")

    def test_action_send_message_no_record(self):
        thread3 = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": 999999,
            }
        )
        with trap_jobs() as trap:
            json_response = (
                '{"title": "Mock Title", "intents": ["greet"], '
                '"direct_response": "Hello"}'
            )
            with patch.object(
                type(self.env["ai.llm.client"]), "chat", return_value=json_response
            ) as mock_chat:
                res = thread3.action_send_message("Testing missing record")
                self.assertEqual(res["status"], "pending")

                trap.perform_enqueued_jobs()

                call_args = mock_chat.call_args_list[-1][0][0]
                self.assertNotIn(
                    "The contextual record name is", call_args[0]["content"]
                )

    def test_get_pending_job_count_computes_correctly(self):
        with patch.object(
            type(self.env["ai.thread"]), "_get_related_jobs"
        ) as mock_get_jobs:
            mock_recordset = MagicMock()
            mock_recordset.__len__.return_value = 1
            mock_recordset.__bool__.return_value = True
            mock_get_jobs.return_value = mock_recordset

            self.assertEqual(self.thread.pending_job_count, 1)

    def test_get_pending_job_count_method(self):
        with patch.object(
            type(self.env["ai.thread"]), "_get_related_jobs"
        ) as mock_get_jobs:
            mock_recordset = MagicMock()
            mock_recordset.__len__.return_value = 1
            mock_get_jobs.return_value = mock_recordset

            count = self.env["ai.thread"].get_pending_job_count(self.thread.id)
            self.assertEqual(count, 1)

    def test_action_cancel_jobs_cancels_enqueued_jobs(self):
        with patch.object(
            type(self.env["ai.thread"]), "_get_related_jobs"
        ) as mock_get_jobs:
            mock_recordset = MagicMock()
            mock_recordset.__len__.return_value = 1
            mock_recordset.__bool__.return_value = True
            mock_get_jobs.return_value = mock_recordset

            with patch.object(type(self.env["bus.bus"]), "_sendone") as mock_sendone:

                def side_effect():
                    mock_recordset.__len__.return_value = 0

                mock_recordset.button_cancelled.side_effect = side_effect

                self.thread.action_cancel_jobs()

                mock_recordset.button_cancelled.assert_called_once()
                self.thread.invalidate_recordset(["pending_job_count"])
                self.assertEqual(self.thread.pending_job_count, 0)
                mock_sendone.assert_called_once()
                call_args = mock_sendone.call_args[0]
                self.assertEqual(call_args[0], self.thread.user_id.partner_id)
                self.assertEqual(call_args[2]["status"], "cancelled")

    def test_action_cancel_jobs_sends_notification_when_empty(self):
        self.assertEqual(self.thread.pending_job_count, 0)

        with patch.object(type(self.env["bus.bus"]), "_sendone") as mock_sendone:
            self.thread.action_cancel_jobs()

            mock_sendone.assert_called_once()
            call_args = mock_sendone.call_args[0]
            self.assertEqual(call_args[0], self.thread.user_id.partner_id)
            self.assertEqual(call_args[2]["status"], "cancelled")

    def test_action_cancel_jobs_with_processing(self):
        """Test action_cancel_jobs when there are processing messages."""
        msg = self.env["ai.message"].create(
            {
                "thread_id": self.thread.id,
                "role": "assistant",
                "status": "processing",
                "content": "",
            }
        )
        self.thread.action_cancel_jobs()
        self.assertEqual(msg.status, "cancel")
        self.assertEqual(msg.content, "Cancelled by user.")

    def test_action_send_message_updates_thread_when_not_new(self):
        self.env["ai.message"].create(
            {
                "thread_id": self.thread.id,
                "role": "user",
                "content": "First message previously sent",
            }
        )

        def mock_chat_side_effect(messages, **kwargs):
            content = messages[-1]["content"] if messages else ""
            if "title" in content.lower():
                return "First message previously sent"
            return "Response"

        with trap_jobs() as trap:
            with patch.object(
                type(self.env["ai.llm.client"]),
                "chat",
                side_effect=mock_chat_side_effect,
            ):
                res = self.thread.action_send_message("Second message")

                self.assertEqual(res["status"], "pending")
                self.assertEqual(res["thread_name"], "First message previously sent")

                messages = self.thread.message_ids.sorted("create_date")
                self.assertEqual(len(messages), 3)
                self.assertEqual(messages[1].role, "user")
                self.assertEqual(messages[1].content, "Second message")

                with patch.object(type(self.env["bus.bus"]), "_sendone"):
                    trap.perform_enqueued_jobs()

                msg = messages[-1]
                self.assertEqual(msg.status, "done")
                self.assertEqual(msg.content, "Response")

    def test_action_send_message_preserves_custom_title(self):
        custom_thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "name": "Custom Title Existing",
            }
        )
        with trap_jobs():
            res = custom_thread.action_send_message("Hello again")
            self.assertEqual(res["thread_name"], "Custom Title Existing")
            self.assertEqual(custom_thread.name, "Custom Title Existing")

    def test_get_full_messages_returns_nested_task_threads(self):
        msg = self.env["ai.message"].create(
            {
                "thread_id": self.thread.id,
                "role": "assistant",
                "status": "processing",
                "content": "Msg Content",
            }
        )
        task_thread = self.env["ai.task.thread"].create(
            {
                "message_id": msg.id,
                "name": "Task Name",
            }
        )
        self.env["ai.task.message"].create(
            {
                "task_thread_id": task_thread.id,
                "role": "user",
                "content": "Task Content",
            }
        )

        res = self.env["ai.thread"].get_full_messages(self.thread.id)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["content"], "Msg Content")
        self.assertEqual(len(res[0]["task_threads"]), 1)
        self.assertEqual(
            res[0]["task_threads"][0]["messages"][0]["content"], "Task Content"
        )

    def test_get_full_messages_returns_empty_when_missing_thread(self):
        res_empty = self.env["ai.thread"].get_full_messages(99999)
        self.assertEqual(res_empty, [])

    def test_queue_job_channel_name(self):
        self.assertEqual(
            self.thread.queue_job_channel_name,
            f"root.ai.thread.id_{self.thread.id}",
        )

    def test_action_generate_thread_title_no_user_msgs(self):
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "name": self.env._("New Thread"),
            }
        )
        thread._action_generate_thread_title()
        self.assertEqual(thread.name, self.env._("New Thread"))

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.AiLlmClient.chat")
    def test_base_process_assistant_message_direct(self, mock_chat):
        from ..models.ai_message import AiMessage as BaseAiMessage

        mock_chat.return_value = "Base LLM response"
        assistant_msg = self.thread._add_message(
            "", role="assistant", status="processing"
        )
        BaseAiMessage._process_assistant_message(assistant_msg)
        self.assertEqual(assistant_msg.status, "done")
        self.assertEqual(assistant_msg.content, "Base LLM response")

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.AiLlmClient.chat")
    def test_base_process_assistant_message_existing_name(self, mock_chat):
        from ..models.ai_message import AiMessage as BaseAiMessage

        mock_chat.return_value = "Base LLM response"
        named_thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "name": "Custom Fixed Name",
            }
        )
        assistant_msg = named_thread._add_message(
            "", role="assistant", status="processing"
        )
        BaseAiMessage._process_assistant_message(assistant_msg)
        self.assertEqual(assistant_msg.status, "done")

    @patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.AiLlmClient.chat")
    def test_base_process_assistant_message_empty_llm_response(self, mock_chat):
        from ..models.ai_message import AiMessage as BaseAiMessage

        mock_chat.return_value = ""
        assistant_msg = self.thread._add_message(
            "", role="assistant", status="processing"
        )
        BaseAiMessage._process_assistant_message(assistant_msg)
        self.assertEqual(assistant_msg.status, "cancel")
        self.assertEqual(assistant_msg.content, "Failed to get a response from LLM.")

    def test_action_generate_thread_title_existing_name(self):
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "name": "Custom Title",
            }
        )
        thread._add_message("User message content", role="user")
        thread._action_generate_thread_title()
        self.assertEqual(thread.name, "Custom Title")

    def test_action_generate_thread_title_empty_first_msg(self):
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "name": self.env._("New Thread"),
            }
        )
        thread._add_message("", role="user")
        thread._action_generate_thread_title()
        self.assertEqual(thread.name, self.env._("New Thread"))

    def test_action_generate_thread_title_base_model(self):
        from ..models.ai_thread import AiThread as BaseAiThread

        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "name": self.env._("New Thread"),
            }
        )
        # 1. No user messages
        BaseAiThread._action_generate_thread_title(thread)
        self.assertEqual(thread.name, self.env._("New Thread"))

        # 2. Empty user message
        thread._add_message("", role="user")
        BaseAiThread._action_generate_thread_title(thread)
        self.assertEqual(thread.name, self.env._("New Thread"))

        # 3. Valid user message on new thread
        thread3 = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "name": self.env._("New Thread"),
            }
        )
        thread3._add_message("Test title generation here", role="user")
        BaseAiThread._action_generate_thread_title(thread3)
        self.assertIn("Test title", thread3.name)

        # 4. Existing name returns early
        BaseAiThread._action_generate_thread_title(thread3)
        self.assertIn("Test title", thread3.name)

    def test_extract_intent_existing_thread_name(self):
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
                "name": "Custom Title",
            }
        )
        msg = thread._add_message("", role="assistant", status="processing")
        with (
            patch.object(type(thread), "_action_generate_thread_title") as mock_title,
            patch.object(type(msg), "_process_assistant_message") as mock_process,
        ):
            msg._action_extract_intent()
            self.assertEqual(thread.name, "Custom Title")
            mock_title.assert_not_called()
            mock_process.assert_called_once()

    def test_task_thread_add_message_payload(self):
        msg = self.thread._add_message("Parent msg", role="user")
        task_thread = self.env["ai.task.thread"].create(
            {"message_id": msg.id, "name": "Task Thread"}
        )
        task_msg = task_thread._add_message(
            "Task msg", role="assistant", payload={"status": "ok"}
        )
        self.assertEqual(task_msg.payload, {"status": "ok"})

    def test_task_thread_add_message_without_payload(self):
        msg = self.thread._add_message("Parent msg", role="user")
        task_thread = self.env["ai.task.thread"].create(
            {"message_id": msg.id, "name": "Task Thread"}
        )
        task_msg = task_thread._add_message("Task msg", role="assistant")
        self.assertFalse(task_msg.payload)

    def test_get_system_prompt_nonexistent_record(self):
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": 999999,
            }
        )
        sys_prompt = thread._get_system_prompt()
        self.assertTrue(sys_prompt)
        self.assertNotIn("contextual record name", sys_prompt[0]["content"])
