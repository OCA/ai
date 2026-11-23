# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.tests import common


class TestOpenWebUIAgentic(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "Agentic OpenWebUI test",
                "url": "https://openwebui.example.com/api/chat/completions",
                "auth_type": "token",
                "auth_token": "sk-test",
                "usage": "chatter",
                "payload_type": "openwebui",
                "result_kind": "immediate",
                "result_type": "message",
                "openwebui_model": "demo",
                "openwebui_web_search": True,
                "openwebui_keep_chat": True,
                "openwebui_timeout": 10,
            }
        )

    def _execution(self):
        return self.env["ai.bridge.execution"].new({"ai_bridge_id": self.bridge.id})

    def _request_mock(self, calls):
        responses = {
            ("POST", "/api/v1/chats/new"): {"id": "chat-1"},
            ("POST", "/api/chat/completions"): {"status": True},
            ("GET", "/api/tasks/chat/chat-1"): {"task_ids": []},
            ("GET", "/api/v1/chats/chat-1"): {
                "chat": {
                    "history": {
                        "messages": {
                            "assistant-1": {
                                "role": "assistant",
                                "content": "Final answer",
                            }
                        }
                    }
                }
            },
        }

        def request(method, url, **kwargs):
            path = url.split(".com", 1)[-1]
            calls.append((method, path, kwargs))
            if method == "DELETE":
                response = mock.Mock(status_code=200, text="", json=lambda: {})
            else:
                response = mock.Mock(
                    status_code=200,
                    text="ack",
                    json=lambda: responses[(method, path)],
                )
            response.raise_for_status.return_value = None
            response.close.return_value = None
            return response

        return request

    def test_agentic_request_contains_chat_identifiers(self):
        execution = self._execution()
        payload = {
            "model": "demo",
            "messages": [{"role": "user", "content": "Hi"}],
        }
        request_payload = execution._openwebui_chat_payload(
            payload, "chat-1", "assistant-1"
        )
        self.assertTrue(request_payload["stream"])
        self.assertEqual(request_payload["chat_id"], "chat-1")
        self.assertEqual(request_payload["id"], "assistant-1")
        self.assertTrue(request_payload["session_id"].startswith("odoo-"))
        self.assertTrue(request_payload["features"]["web_search"])

    def test_agentic_flow_keeps_question_and_chat(self):
        execution = self._execution()
        calls = []
        with (
            mock.patch("requests.request", side_effect=self._request_mock(calls)),
            mock.patch(
                "odoo.addons.ai_oca_bridge_openwebui.models.ai_bridge_execution.uuid.uuid4",
                side_effect=["assistant-1", "user-1", "session-1"],
            ),
        ):
            result = execution._openwebui_execute_agentic(
                {"model": "demo", "messages": [{"role": "user", "content": "Hi"}]}
            )

        self.assertEqual(
            result["completion"]["choices"][0]["message"]["content"],
            "Final answer",
        )
        self.assertEqual(
            [call[:2] for call in calls],
            [
                ("POST", "/api/v1/chats/new"),
                ("POST", "/api/chat/completions"),
                ("GET", "/api/tasks/chat/chat-1"),
                ("GET", "/api/v1/chats/chat-1"),
            ],
        )
        create_chat = calls[0][2]["json"]["chat"]
        user_message = next(
            message
            for message in create_chat["history"]["messages"].values()
            if message["role"] == "user"
        )
        self.assertEqual(user_message["content"], "Hi")
        self.assertEqual(user_message["childrenIds"], ["assistant-1"])
        completion_call = calls[1][2]
        self.assertTrue(completion_call["stream"])
        self.assertEqual(completion_call["json"]["chat_id"], "chat-1")
        self.assertEqual(completion_call["json"]["id"], "assistant-1")
        self.assertTrue(completion_call["json"]["features"]["web_search"])

    def test_agentic_flow_deletes_chat_when_disabled(self):
        self.bridge.openwebui_keep_chat = False
        execution = self._execution()
        calls = []
        with (
            mock.patch("requests.request", side_effect=self._request_mock(calls)),
            mock.patch(
                "odoo.addons.ai_oca_bridge_openwebui.models.ai_bridge_execution.uuid.uuid4",
                side_effect=["assistant-1", "user-1", "session-1"],
            ),
        ):
            execution._openwebui_execute_agentic(
                {"model": "demo", "messages": [{"role": "user", "content": "Hi"}]}
            )
        self.assertEqual(calls[-1][:2], ("DELETE", "/api/v1/chats/chat-1"))
