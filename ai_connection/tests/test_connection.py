# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from freezegun import freeze_time
from odoo_test_helper import FakeModelLoader

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestConnection(TransactionCase):
    def setUp(self):
        super().setUp()
        self.loader = FakeModelLoader(self.env, self.__module__)
        self.loader.backup_registry()
        from .fake_models import AiConnection, AiConnectionTestTool

        self.loader.update_registry((AiConnection, AiConnectionTestTool))
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

    def _demo_connection(self):
        return self.env["ai.connection"].create({"name": "Demo", "kind": "demo"})

    def test_tool_error_is_answered_to_the_ai(self):
        # post_message needs a record: without one it raises ValueError
        tool = self.env.ref("ai_tool.post_message")
        response = self._demo_connection()._run(
            'call:post_message {"message": "hi"}', tools=tool
        )
        self.assertIn("Record must be provided", response[0])
        self.assertIn("ValueError", response[0])
        self.assertEqual(response[3], 2)

    def test_unknown_tool_is_answered_to_the_ai(self):
        tool = self.env.ref("ai_tool.current_date")
        response = self._demo_connection()._run("call:does_not_exist", tools=tool)
        self.assertIn("ToolNotFound", response[0])
        self.assertIn("does_not_exist", response[0])
        self.assertEqual(response[3], 2)

    def test_unknown_tool_without_tools(self):
        response = self._demo_connection()._run("call:does_not_exist")
        self.assertIn("ToolNotFound", response[0])

    def test_on_step_events(self):
        tool = self.env.ref("ai_tool.current_date")
        steps = []
        with freeze_time("2024-01-01"):
            response = self._demo_connection()._run(
                "call:get_date", tools=tool, on_step=steps.append
            )
        self.assertEqual(
            [step["type"] for step in steps],
            [
                "llm_call",
                "iteration",
                "tool_call",
                "tool_result",
                "llm_call",
                "iteration",
            ],
        )
        steps = [step for step in steps if step["type"] != "llm_call"]
        self.assertEqual(steps[0]["iteration"], 1)
        self.assertEqual(steps[1]["tool"], "get_date")
        self.assertEqual(steps[1]["call_id"], "call_1")
        self.assertEqual(steps[2]["result"], {"date": "2024-01-01"})
        self.assertIsNone(steps[2]["error"])
        self.assertEqual(steps[3]["iteration"], 2)
        self.assertEqual(steps[3]["content"], response[0])

    def test_next_iteration_elsewhere(self):
        tool = self.env.ref("ai_tool.current_date")
        states = []
        with freeze_time("2024-01-01"):
            response = self._demo_connection()._run(
                "call:get_date", tools=tool, next_iteration=states.append
            )
            # The first iteration ran the tool and handed over the rest
            self.assertIsNone(response)
            self.assertEqual(len(states), 1)
            state = states[0]
            self.assertEqual(state["iteration"], 2)
            self.assertEqual(
                [m["role"] for m in state["messages"]], ["user", "assistant", "tool"]
            )
            json.dumps(state)
            steps = []
            response = self._demo_connection()._run(
                messages=state["messages"],
                iteration=state["iteration"],
                tools=tool,
                on_step=steps.append,
                next_iteration=states.append,
            )
        # The tool is not called again: the AI goes on from its result
        self.assertEqual([s["type"] for s in steps], ["llm_call", "iteration"])
        self.assertEqual(steps[1]["iteration"], 2)
        self.assertIn("2024-01-01", response[0])
        self.assertEqual(response[3], 2)

    def test_max_iterations_across_calls(self):
        tool = self.env.ref("ai_tool.current_date")
        with self.assertRaises(UserError):
            self._demo_connection()._run(
                "call:get_date", tools=tool, iteration=3, max_iterations=2
            )

    def test_on_step_tool_error(self):
        tool = self.env.ref("ai_tool.post_message")
        steps = []
        self._demo_connection()._run(
            'call:post_message {"message": "hi"}', tools=tool, on_step=steps.append
        )
        self.assertIn("Record must be provided", steps[3]["error"])

    def test_tool_activity_injected_only_on_demand(self):
        tool = self.env.ref("ai_tool.current_date")
        definition = tool._get_tool_definition()
        self.assertNotIn("activity", definition["inputSchema"]["properties"])
        definition = tool.with_context(ai_tool_activity=True)._get_tool_definition()
        self.assertIn("activity", definition["inputSchema"]["properties"])
        self.assertIn("activity", definition["inputSchema"]["required"])
        # The shared schema of the decorated method is not modified
        definition = tool._get_tool_definition()
        self.assertNotIn("activity", definition["inputSchema"]["properties"])

    def test_tool_activity_removed_before_running_the_tool(self):
        tool = self.env.ref("ai_tool.current_date")
        steps = []
        with freeze_time("2024-01-01"):
            # _ai_get_date() takes no arguments: it would fail with activity
            response = self._demo_connection()._run(
                'call:get_date {"activity": "Checking the date..."}',
                tools=tool,
                on_step=steps.append,
                tool_activity=True,
            )
        self.assertEqual(
            response[0], 'This is a demo response to the prompt: {"date": "2024-01-01"}'
        )
        self.assertEqual(steps[2]["activity"], "Checking the date...")
        self.assertNotIn("activity", steps[2]["arguments"])

    def test_tool_activity_kept_without_injection(self):
        tool = self.env.ref("ai_tool.current_date")
        steps = []
        self._demo_connection()._run(
            'call:get_date {"activity": "x"}', tools=tool, on_step=steps.append
        )
        # Not injected, so not removed: the tool rejects the unknown argument
        self.assertIsNone(steps[2]["activity"])
        self.assertIn("activity", steps[3]["error"])

    def test_tool_activity_not_injected_when_tool_defines_it(self):
        tool = self.env["ai.tool"].create(
            {
                "name": "echo_activity",
                "model_id": self.env["ir.model"]._get("ai.connection.test.tool").id,
                "function_name": "_ai_echo_activity",
                "kind": "generic",
            }
        )
        definition = tool.with_context(ai_tool_activity=True)._get_tool_definition()
        self.assertEqual(definition["inputSchema"]["required"], ["activity"])
        steps = []
        self._demo_connection()._run(
            'call:echo_activity {"activity": "own"}',
            tools=tool,
            on_step=steps.append,
            tool_activity=True,
        )
        # The argument belongs to the tool: it is neither removed nor reported
        self.assertIsNone(steps[2]["activity"])
        self.assertEqual(steps[3]["result"], {"activity": "own"})
