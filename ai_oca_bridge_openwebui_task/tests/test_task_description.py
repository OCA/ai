# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import Mock, patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools.mail import html2plaintext


@tagged("post_install", "-at_install")
class TestOpenWebuiTaskDescription(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.project = cls.env["project.project"].create({"name": "Test project"})
        cls.task = cls.env["project.task"].create(
            {
                "name": "Prepare the site visit",
                "project_id": cls.project.id,
                "description": "<p>Check the equipment.</p>",
            }
        )
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "Task description OpenWebUI",
                "active": True,
                "payload_type": "openwebui",
                "usage": "project_task",
                "result_kind": "immediate",
                "result_type": "none",
                "url": "https://openwebui.example/api/chat/completions",
                "auth_type": "token",
                "auth_token": "test-token",
                "openwebui_model": "test-model",
            }
        )

    def test_generate_description_opens_review_wizard(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [
                {"message": {"role": "assistant", "content": "Inspect the router."}}
            ]
        }
        with patch("requests.request", return_value=response) as request_mock:
            action = self.task.action_openwebui_draft_description()

        self.assertEqual(
            action["res_model"], "ai.oca.bridge.openwebui.task.description.wizard"
        )
        wizard = self.env[action["res_model"]].browse(action["res_id"])
        self.assertEqual(
            html2plaintext(wizard.description).strip(), "Inspect the router."
        )
        self.assertEqual(request_mock.call_args.kwargs["json"]["model"], "test-model")
        self.assertIn(
            "Prepare the site visit",
            request_mock.call_args.kwargs["json"]["messages"][-1]["content"],
        )

    def test_missing_task_bridge_is_reported(self):
        self.bridge.unlink()
        with self.assertRaises(UserError):
            self.task.action_openwebui_draft_description()
