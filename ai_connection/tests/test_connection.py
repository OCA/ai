# Copyright 2026 Dixmit
# Copyright 2026 SDi <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from freezegun import freeze_time
from odoo_test_helper import FakeModelLoader

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

from ..client import AiConnectionClient
from .fake_models import AiConnection


class TestConnection(TransactionCase):
    def setUp(self):
        super().setUp()
        self.loader = FakeModelLoader(self.env, self.__module__)
        self.loader.backup_registry()

        self.loader.update_registry((AiConnection,))
        self.addCleanup(self.loader.restore_registry)

    def test_demo_connection(self):
        connection = self.env["ai.connection"].create(
            {
                "name": "Demo Connection",
                "kind": "demo",
            }
        )
        response = connection._run("Hello, AI!")
        self.assertEqual(
            response[0], "This is a demo response to the prompt: Hello, AI!"
        )
        self.assertEqual(response[3], 1)

    def test_demo_connection_with_attachment(self):
        attachment = self.env["ir.attachment"].create(
            {
                "name": "test.txt",
                "datas": "SGVsbG8sIEFJIQ==",  # Base64 for "Hello, AI!"
                "mimetype": "text/plain",
            }
        )
        connection = self.env["ai.connection"].create(
            {
                "name": "Demo Connection",
                "kind": "demo",
            }
        )
        response = connection._run(attachments=attachment)
        self.assertEqual(
            response[0], "This is a demo response to the prompt: Hello, AI!"
        )
        self.assertEqual(response[3], 1)

    def test_demo_connection_with_tool(self):
        tool = self.env.ref("ai_tool.current_date")
        connection = self.env["ai.connection"].create(
            {
                "name": "Demo Connection",
                "kind": "demo",
            }
        )
        with freeze_time("2024-01-01"):
            response = connection._run("get_date", tools=tool)
        self.assertEqual(
            response[0], 'This is a demo response to the prompt: {"date": "2024-01-01"}'
        )
        self.assertEqual(response[3], 2)

    def test_demo_connection_max_iterations(self):
        tool = self.env.ref("ai_tool.current_date")
        connection = self.env["ai.connection"].create(
            {
                "name": "Demo Connection",
                "kind": "demo",
            }
        )
        with self.assertRaises(UserError):
            connection._run("get_date", tools=tool, max_iterations=1)

    def test_demo_connection_persistent(self):
        connection = self.env["ai.connection"].create(
            {
                "name": "Demo Connection",
                "kind": "demo",
            }
        )
        execution = connection._run("Hello, AI!", store=True)
        self.assertEqual(execution.state, "done")
        self.assertEqual(
            execution.result_content,
            "This is a demo response to the prompt: Hello, AI!",
        )
        self.assertTrue(execution.messages_json)
        self.assertEqual(execution.current_iteration, 1)

    def test_demo_connection_stepwise(self):
        tool = self.env.ref("ai_tool.current_date")
        connection = self.env["ai.connection"].create(
            {
                "name": "Demo Connection",
                "kind": "demo",
            }
        )
        with freeze_time("2024-01-01"):
            execution = connection._run(
                "get_date", tools=tool, store=True, stepwise=True
            )
            self.assertEqual(execution.state, "paused")
            self.assertEqual(execution.current_iteration, 1)

            # Resume
            execution.action_step()
            self.assertEqual(execution.state, "done")
            self.assertEqual(execution.current_iteration, 2)
            self.assertEqual(
                execution.result_content,
                'This is a demo response to the prompt: {"date": "2024-01-01"}',
            )

    def test_demo_connection_streaming(self):
        connection = self.env["ai.connection"].create(
            {
                "name": "Demo Connection",
                "kind": "demo",
            }
        )
        execution = connection._run("Hello, AI!", store=True, stream=True)
        self.assertEqual(execution.state, "done")

    def test_demo_connection_attachment_extraction(self):
        attachment = self.env["ir.attachment"].create(
            {
                "name": "test.txt",
                "datas": "SGVsbG8sIEFJIQ==",
                "mimetype": "text/plain",
            }
        )
        connection = self.env["ai.connection"].create(
            {
                "name": "Demo Connection",
                "kind": "demo",
            }
        )
        execution = connection._run("dummy", attachments=attachment, store=True)
        self.assertEqual(execution.state, "done")

        messages = execution.messages_json
        user_message = next(msg for msg in messages if msg["role"] == "user")
        self.assertIn("attachment_id", user_message["files"][0])
        self.assertNotIn("content", user_message["files"][0])

    def test_execution_actions_early_returns(self):
        execution = self.env["ai.connection.execution"].create(
            {
                "connection_id": self.env["ai.connection"]
                .create({"name": "C", "kind": "demo"})
                .id,
                "state": "done",
            }
        )
        self.assertIsNone(execution.action_start())
        self.assertIsNone(execution.action_step())
        self.assertIsNone(execution.action_resume())

    def test_execution_resume(self):
        tool = self.env.ref("ai_tool.current_date")
        connection = self.env["ai.connection"].create({"name": "C", "kind": "demo"})
        with freeze_time("2024-01-01"):
            execution = connection._run(
                "get_date", tools=tool, store=True, stepwise=True
            )
            self.assertEqual(execution.state, "paused")
            execution.action_resume()
            self.assertEqual(execution.state, "done")
            self.assertFalse(execution.stepwise)

    def test_execution_max_iterations_failed(self):
        tool = self.env.ref("ai_tool.current_date")
        connection = self.env["ai.connection"].create({"name": "C", "kind": "demo"})
        execution = self.env["ai.connection.execution"].create(
            {
                "connection_id": connection.id,
                "prompt": "get_date",
                "messages_json": [{"role": "user", "content": "get_date"}],
                "max_iterations": 1,
                "tool_ids": [(6, 0, tool.ids)],
            }
        )
        execution.action_start()
        # The mock tool runs, then we hit iteration > max
        # Wait, if max_iteration is 1, it runs iteration 1, calls tool, tool returns.
        # Then next step it sees current_iteration >= max_iterations and fails.
        if execution.state == "paused":
            execution.action_resume()
        self.assertEqual(execution.state, "failed")
        self.assertEqual(execution.error_message, "Max iterations reached.")

    def test_compute_total_tokens(self):
        execution = self.env["ai.connection.execution"].create(
            {
                "connection_id": self.env["ai.connection"]
                .create({"name": "C", "kind": "demo"})
                .id,
                "prompt_tokens": 10,
                "completion_tokens": 5,
            }
        )
        self.assertEqual(execution.total_tokens, 15)

    def test_pending_tool_approval(self):
        # Override _should_execute_tool to return False
        connection = self.env["ai.connection"].create({"name": "C", "kind": "demo"})
        tool = self.env.ref("ai_tool.current_date")
        execution = self.env["ai.connection.execution"].create(
            {
                "connection_id": connection.id,
                "prompt": "get_date",
                "messages_json": [{"role": "user", "content": "get_date"}],
                "tool_ids": [(6, 0, tool.ids)],
            }
        )

        with patch.object(type(execution), "_should_execute_tool", return_value=False):
            execution.action_start()

        self.assertEqual(execution.state, "pending_tool_approval")

    def test_execution_iteration_autovacuum(self):
        execution = self.env["ai.connection.execution"].create(
            {
                "connection_id": self.env["ai.connection"]
                .create({"name": "C", "kind": "demo"})
                .id
            }
        )
        it = self.env["ai.connection.execution.iteration"].create(
            {
                "execution_id": execution.id,
                "step_number": 1,
            }
        )
        # Mock create_date
        self.env.cr.execute(
            "UPDATE ai_connection_execution_iteration SET create_date=%s WHERE id=%s",
            (fields.Datetime.now() - relativedelta(days=20), it.id),
        )
        self.env["ai.connection.execution.iteration"]._autovacuum()
        self.assertFalse(it.exists())

    @mute_logger("odoo.addons.ai_connection.models.ai_connection")
    def test_tool_execution_error_caught(self):
        tool = self.env.ref("ai_tool.current_date")
        connection = self.env["ai.connection"].create({"name": "C", "kind": "demo"})

        with patch.object(
            type(tool), "_execute_tool", side_effect=ValueError("Tool failed!")
        ):
            response = connection._run("get_date", tools=tool)
            self.assertIn("Tool failed!", response[0])

    def test_demo_connection_streaming_batch(self):
        connection = self.env["ai.connection"].create({"name": "C", "kind": "demo"})
        with patch.object(
            type(self.env["ai.connection.execution"]), "_on_stream_batch"
        ) as mock_stream:
            execution = connection._run(
                "test", store=True, stream=True, stream_batch_size=1
            )
            self.assertEqual(execution.state, "done")
            # Should have been called multiple times
            # since batch size is 1 and chunks = 2
            self.assertTrue(mock_stream.call_count >= 2)

    @mute_logger("odoo.addons.ai_connection.models.ai_connection_execution")
    def test_execution_step_error_caught(self):
        connection = self.env["ai.connection"].create({"name": "C", "kind": "demo"})
        execution = self.env["ai.connection.execution"].create(
            {
                "connection_id": connection.id,
                "prompt": "test",
            }
        )
        with patch.object(
            type(connection), "_execute_ai_call", side_effect=ValueError("AI exploded!")
        ):
            execution.action_start()
            self.assertEqual(execution.state, "failed")
            self.assertEqual(execution.error_message, "AI exploded!")

    def test_rehydrate_missing_attachment(self):
        connection = self.env["ai.connection"].create({"name": "C", "kind": "demo"})
        execution = self.env["ai.connection.execution"].create(
            {
                "connection_id": connection.id,
                "messages_json": [
                    {
                        "role": "user",
                        "content": "test",
                        "files": [{"attachment_id": 9999999, "name": "gone.txt"}],
                    }
                ],
            }
        )
        # The rehydrate should ignore the missing attachment
        rehydrated = execution._rehydrate_messages(execution.messages_json)
        self.assertEqual(len(rehydrated[0]["files"]), 0)

    def test_extract_attachments_bytes_and_strings(self):
        execution = self.env["ai.connection.execution"].create(
            {
                "connection_id": self.env["ai.connection"]
                .create({"name": "C", "kind": "demo"})
                .id,
            }
        )
        msg = {
            "files": [
                {"name": "str.txt", "content": "string content"},
                {"name": "bytes.txt", "content": b"bytes content"},
            ]
        }
        res = execution._extract_attachments(msg)
        self.assertEqual(len(res["files"]), 2)
        self.assertTrue(all("attachment_id" in f for f in res["files"]))

    def test_client_not_implemented(self):
        client = AiConnectionClient()
        with self.assertRaises(NotImplementedError):
            client.handle_message()

    def test_execution_iteration_txt_fields(self):
        execution = self.env["ai.connection.execution"].create(
            {
                "connection_id": self.env["ai.connection"]
                .create({"name": "C", "kind": "demo"})
                .id
            }
        )
        it = self.env["ai.connection.execution.iteration"].create(
            {
                "execution_id": execution.id,
                "step_number": 1,
                "request_messages_json": [{"role": "user", "content": "hi"}],
                "response_message_json": {"role": "assistant", "content": "hello"},
                "tool_calls_json": [{"name": "tool"}],
                "tool_results_json": [{"role": "tool", "content": "result"}],
            }
        )
        self.assertIn('"hi"', it.request_messages_txt)
        self.assertIn('"hello"', it.response_message_txt)
        self.assertIn('"tool"', it.tool_calls_txt)
        self.assertIn('"result"', it.tool_results_txt)

        # test empty ones
        it2 = self.env["ai.connection.execution.iteration"].create(
            {
                "execution_id": execution.id,
                "step_number": 2,
            }
        )
        self.assertEqual(it2.request_messages_txt, "")
        self.assertEqual(it2.response_message_txt, "")
        self.assertEqual(it2.tool_calls_txt, "")
        self.assertEqual(it2.tool_results_txt, "")

    def test_client_fallback_stream(self):
        connection = self.env["ai.connection"].create({"name": "C", "kind": "demo"})

        class NoStreamClient:
            def handle_message(self, messages, temperature=None):
                return {
                    "message": {"content": "hello"},
                    "tool_calls": [{"name": "tool"}],
                    "usage": {"prompt_tokens": 1},
                }

        no_stream = NoStreamClient()
        stream_method = connection._get_stream_method(no_stream)
        chunks = list(stream_method([{"role": "user", "content": "hi"}]))
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0]["content"], "hello")
        self.assertEqual(chunks[1]["tool_calls"][0]["name"], "tool")
        self.assertEqual(chunks[2]["usage"]["prompt_tokens"], 1)

    def test_system_prompt_handling(self):
        connection = self.env["ai.connection"].create({"name": "C", "kind": "demo"})
        execution = connection._run("Hello", system_prompt="Be nice", store=True)
        messages = execution.messages_json
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], "Be nice")
        self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(messages[1]["content"], "Hello")

    def test_run_with_record(self):
        connection = self.env["ai.connection"].create({"name": "C", "kind": "demo"})
        execution = connection._run("Hello", record=connection, store=True)
        self.assertEqual(execution.res_model, connection._name)
        self.assertEqual(execution.res_id, connection.id)

    def test_only_system_prompt(self):
        connection = self.env["ai.connection"].create({"name": "C", "kind": "demo"})
        execution = connection._run(system_prompt="Be nice", store=True)
        self.assertEqual(len(execution.messages_json), 2)
        self.assertEqual(execution.messages_json[0]["role"], "system")
        self.assertEqual(execution.messages_json[1]["role"], "assistant")

    def test_run_ai_pending_approval(self):
        connection = self.env["ai.connection"].create({"name": "C", "kind": "demo"})
        tool = self.env.ref("ai_tool.current_date")
        execution = self.env["ai.connection.execution"].create(
            {"connection_id": connection.id}
        )
        with patch.object(type(execution), "_should_execute_tool", return_value=False):
            with self.assertRaises(UserError):
                connection._run_ai(
                    [{"role": "user", "content": "get_date"}],
                    tools=tool,
                    execution_record=execution,
                )

    def test_run_with_debug(self):
        connection = self.env["ai.connection"].create({"name": "C", "kind": "demo"})
        execution = connection._run("Hello", debug=True, store=True)
        self.assertEqual(execution.state, "done")
        self.assertTrue(len(execution.iteration_ids) > 0)

    def test_rehydrate_without_attachment_id(self):
        execution = self.env["ai.connection.execution"].create(
            {
                "connection_id": self.env["ai.connection"]
                .create({"name": "C", "kind": "demo"})
                .id,
            }
        )
        msg = {
            "files": [
                {"name": "str.txt", "content": "string content"},
            ]
        }
        res = execution._rehydrate_messages([msg])
        self.assertEqual(len(res[0]["files"]), 1)
        self.assertNotIn("attachment_id", res[0]["files"][0])
