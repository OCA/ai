# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

import requests

from odoo.tests import TransactionCase, mute_logger, new_test_user


class TestOpenWebUIExecutionEdgeCases(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "OpenWebUI edge case test",
                "url": "https://openwebui.example/api/chat/completions",
                "auth_type": "token",
                "auth_token": "test-token",
                "payload_type": "openwebui",
                "usage": "chatter",
                "result_kind": "immediate",
                "result_type": "message",
                "openwebui_model": "test-model",
                "openwebui_timeout": 5,
            }
        )
        cls.ai_user = new_test_user(
            cls.env, login="openwebui-edge-ai", groups="base.group_user"
        )
        cls.ai_user.write({"ai_bridge_id": cls.bridge.id})
        cls.partner = cls.env["res.partner"].create({"name": "Edge case partner"})
        cls.message = (
            cls.env["mail.message"]
            .sudo()
            .create(
                {
                    "author_id": cls.env.user.partner_id.id,
                    "body": "Question",
                    "model": "res.partner",
                    "res_id": cls.partner.id,
                    "message_type": "comment",
                    "subtype_id": cls.env.ref("mail.mt_comment").id,
                }
            )
        )

    def _create_message(self, model, res_id, body, **kwargs):
        values = {
            "author_id": self.env.user.partner_id.id,
            "body": body,
            "model": model,
            "res_id": res_id,
            "message_type": "comment",
            "subtype_id": self.env.ref("mail.mt_comment").id,
        }
        values.update(kwargs)
        return self.env["mail.message"].sudo().create(values)

    def _execution(self, message=None, chatter_user=True):
        return (
            self.env["ai.bridge.execution"]
            .sudo()
            .new(
                {
                    "ai_bridge_id": self.bridge.id,
                    "model_id": self.env.ref("mail.model_mail_message").id,
                    "res_id": message.id if message else 999999,
                    "chatter_user_id": self.ai_user.id if chatter_user else False,
                }
            )
        )

    def test_get_channel_rejects_missing_and_unknown_targets(self):
        execution_class = (
            "odoo.addons.ai_oca_bridge_openwebui_discuss.models."
            "ai_bridge_execution.AiBridgeExecution"
        )
        with self.assertRaisesRegex(ValueError, "could not be found"):
            self._execution()._get_channel()
        unknown = self.env["mail.message"].new({"model": "missing.model", "res_id": 1})
        with (
            mock.patch(
                f"{execution_class}._openwebui_message_record",
                return_value=unknown,
            ),
            self.assertRaisesRegex(ValueError, "Unknown chatter model"),
        ):
            self._execution(self.message)._get_channel()
        missing_partner = self.env["mail.message"].new(
            {"model": "res.partner", "res_id": 999999}
        )
        with (
            mock.patch(
                f"{execution_class}._openwebui_message_record",
                return_value=missing_partner,
            ),
            self.assertRaisesRegex(ValueError, "target could not be found"),
        ):
            self._execution(self.message)._get_channel()

    def test_agentic_payload_includes_selected_tools(self):
        self.bridge.openwebui_web_search = True
        execution = self._execution(self.message)
        payload = execution._openwebui_chat_payload(
            {"model": "test-model", "messages": [], "tool_ids": ["search"]},
            "chat-id",
            "assistant-id",
        )
        self.assertEqual(payload["tool_ids"], ["search"])
        self.assertTrue(payload["features"]["web_search"])
        self.assertFalse(payload["features"]["memory"])

    def test_create_chat_rejects_missing_openwebui_chat_id(self):
        response = mock.Mock()
        response.json.return_value = {}
        execution = self._execution(self.message)
        with mock.patch(
            "odoo.addons.ai_oca_bridge_openwebui_discuss.models.ai_bridge_execution."
            "AiBridgeExecution._openwebui_request",
            return_value=response,
        ):
            with self.assertRaisesRegex(ValueError, "temporary chat ID"):
                execution._openwebui_create_chat(
                    {"model": "test-model", "messages": []}, "assistant-id"
                )

    def test_poll_chat_times_out_when_openwebui_task_never_finishes(self):
        response = mock.Mock()
        response.json.return_value = {"task_ids": ["task-id"]}
        execution = self._execution(self.message)
        with (
            mock.patch(
                "odoo.addons.ai_oca_bridge_openwebui_discuss.models.ai_bridge_execution.time.monotonic",
                side_effect=[0, 1, 6],
            ),
            mock.patch(
                "odoo.addons.ai_oca_bridge_openwebui_discuss.models.ai_bridge_execution."
                "AiBridgeExecution._openwebui_request",
                return_value=response,
            ),
            mock.patch(
                "odoo.addons.ai_oca_bridge_openwebui_discuss.models.ai_bridge_execution."
                "AiBridgeExecution._openwebui_sleep"
            ),
        ):
            with self.assertRaisesRegex(TimeoutError, "did not finish"):
                execution._openwebui_poll_chat("chat-id")

    def test_read_chat_rejects_missing_assistant_message(self):
        response = mock.Mock()
        response.json.return_value = {"chat": {"history": {"messages": {}}}}
        execution = self._execution(self.message)
        with mock.patch(
            "odoo.addons.ai_oca_bridge_openwebui_discuss.models.ai_bridge_execution."
            "AiBridgeExecution._openwebui_request",
            return_value=response,
        ):
            with self.assertRaisesRegex(ValueError, "assistant message"):
                execution._openwebui_read_chat("chat-id", "assistant-id")

    def test_must_answer_rejects_empty_or_non_user_context(self):
        execution = self._execution(self.message)
        self.assertFalse(execution._openwebui_must_answer(self.env["mail.message"], {}))
        self.assertFalse(
            execution._openwebui_must_answer(
                self.message, {"messages": [{"role": "assistant", "content": "Hi"}]}
            )
        )

    def test_delete_chat_failure_is_logged_and_ignored(self):
        execution = self._execution(self.message)
        with (
            mute_logger(
                "odoo.addons.ai_oca_bridge_openwebui_discuss.models.ai_bridge_execution"
            ),
            mock.patch(
                "odoo.addons.ai_oca_bridge_openwebui_discuss.models.ai_bridge_execution."
                "AiBridgeExecution._openwebui_request",
                side_effect=requests.ConnectionError("offline"),
            ),
        ):
            self.assertIsNone(execution._openwebui_delete_chat("chat-id"))

    def test_stop_typing_is_noop_without_chatter_user(self):
        execution = self._execution(self.message, chatter_user=False)
        self.assertIsNone(execution._openwebui_stop_typing())
