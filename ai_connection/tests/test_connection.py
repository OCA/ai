# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from freezegun import freeze_time
from odoo_test_helper import FakeModelLoader

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

from odoo.addons.ai_connection.client import AiConnectionClient


class TestConnection(TransactionCase):
    def setUp(self):
        super().setUp()
        self.loader = FakeModelLoader(self.env, self.__module__)
        self.loader.backup_registry()
        from .fake_models import AiConnection

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

    def test_demo_connection_with_system_prompt(self):
        connection = self.env["ai.connection"].create(
            {
                "name": "Demo Connection",
                "kind": "demo",
            }
        )
        messages = []
        response = connection._run(
            "Hello, AI!", system_prompt="Answer briefly.", messages=messages
        )
        self.assertEqual(
            response[0], "This is a demo response to the prompt: Hello, AI!"
        )
        self.assertEqual(messages[0], {"role": "system", "content": "Answer briefly."})

    def test_demo_connection_with_failing_tool(self):
        # Posting a message needs a record: the error of the tool does not
        # stop the conversation.
        tool = self.env.ref("ai_tool.post_message")
        connection = self.env["ai.connection"].create(
            {
                "name": "Demo Connection",
                "kind": "demo",
            }
        )
        response = connection._run("post_message", tools=tool)
        self.assertEqual(response[3], 2)

    def test_client_must_handle_messages(self):
        with self.assertRaises(NotImplementedError):
            AiConnectionClient().handle_message(messages=[])
