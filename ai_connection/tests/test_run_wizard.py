# Copyright 2026 SDi
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestAiConnectionRunWizard(TransactionCase):
    def setUp(self):
        super().setUp()
        from odoo_test_helper import FakeModelLoader

        self.loader = FakeModelLoader(self.env, self.__module__)
        self.loader.backup_registry()
        from .fake_models import AiConnection

        self.loader.update_registry((AiConnection,))
        self.addCleanup(self.loader.restore_registry)

        self.connection = self.env["ai.connection"].create(
            {
                "name": "Test Connection",
                "kind": "demo",
            }
        )

    def test_action_run_store(self):
        wizard = self.env["ai.connection.run.wizard"].create(
            {
                "connection_id": self.connection.id,
                "prompt": "Test prompt",
                "store": True,
            }
        )
        with patch(
            "odoo.addons.ai_connection.models.ai_connection.AiConnection._run"
        ) as mock_run:
            mock_execution = self.env["ai.connection.execution"].create(
                {
                    "connection_id": self.connection.id,
                    "prompt": "Test prompt",
                }
            )
            mock_run.return_value = mock_execution
            action = wizard.action_run()
            self.assertEqual(action["type"], "ir.actions.act_window")
            self.assertEqual(action["res_model"], "ai.connection.execution")
            self.assertEqual(action["res_id"], mock_execution.id)

    def test_action_run_async(self):
        wizard = self.env["ai.connection.run.wizard"].create(
            {
                "connection_id": self.connection.id,
                "prompt": "Test async prompt",
                "store": True,
                "is_async": True,
            }
        )
        with patch(
            "odoo.addons.ai_connection.models.ai_connection.AiConnection._run"
        ) as mock_run:
            mock_execution = self.env["ai.connection.execution"].create(
                {
                    "connection_id": self.connection.id,
                    "prompt": "Test async prompt",
                    "is_async": True,
                }
            )
            mock_run.return_value = mock_execution
            action = wizard.action_run()
            self.assertEqual(action["type"], "ir.actions.act_window")
            self.assertEqual(action["res_model"], "ai.connection.execution")
            self.assertEqual(action["res_id"], mock_execution.id)
            mock_run.assert_called_once_with(
                prompt="Test async prompt",
                system_prompt=False,
                tools=self.env["ai.tool"],
                store=True,
                stepwise=False,
                debug=False,
                stream=False,
                stream_batch_size=40,
                max_iterations=50,
                is_async=True,
            )

    def test_action_run_no_store(self):
        wizard = self.env["ai.connection.run.wizard"].create(
            {
                "connection_id": self.connection.id,
                "prompt": "Test prompt",
                "store": False,
            }
        )
        with patch(
            "odoo.addons.ai_connection.models.ai_connection.AiConnection._run"
        ) as mock_run:
            mock_run.return_value = ("Test response", 10, 20, 1)
            action = wizard.action_run()
            self.assertEqual(action["type"], "ir.actions.act_window")
            self.assertEqual(action["res_model"], "ai.connection.run.wizard")
            self.assertEqual(wizard.response_content, "Test response")
