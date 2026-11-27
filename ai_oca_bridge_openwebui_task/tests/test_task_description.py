# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import Mock, patch

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged
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

    def _completion_response(self, content="Inspect the router."):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": content}}]
        }
        return response

    def test_generate_description_opens_review_wizard(self):
        tag = self.env["project.tags"].create({"name": "Onsite"})
        self.task.write(
            {
                "date_deadline": "2026-12-01",
                "user_ids": [(6, 0, [self.env.user.id])],
                "tag_ids": [(6, 0, [tag.id])],
            }
        )
        with patch(
            "requests.request", return_value=self._completion_response()
        ) as request_mock:
            action = self.task.action_openwebui_draft_description()

        self.assertEqual(
            action["res_model"], "ai.oca.bridge.openwebui.task.description.wizard"
        )
        wizard = self.env[action["res_model"]].browse(action["res_id"])
        self.assertEqual(
            html2plaintext(wizard.description).strip(), "Inspect the router."
        )
        # The generator only proposes content; it does not update the task yet.
        self.assertIn("Check the equipment", self.task.description)
        payload = request_mock.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "test-model")
        task_prompt = payload["messages"][-1]["content"]
        self.assertIn("Prepare the site visit", task_prompt)
        self.assertIn("Deadline: 2026-12-01", task_prompt)
        self.assertIn("Assignees:", task_prompt)
        self.assertIn("Tags: Onsite", task_prompt)

        wizard.description = "<p>Reviewed description</p>"
        wizard.action_apply()
        self.assertIn("Reviewed description", self.task.description)

    def test_missing_task_bridge_is_reported(self):
        self.bridge.unlink()
        with self.assertRaises(UserError):
            self.task.action_openwebui_draft_description()

    def test_bridge_group_and_model_restrictions_are_enforced(self):
        restricted_group = self.env["res.groups"].create({"name": "Task AI restricted"})
        self.bridge.group_ids = [(6, 0, [restricted_group.id])]
        with self.assertRaises(AccessError):
            self.task.action_openwebui_draft_description()

        self.bridge.group_ids = False
        partner_model = self.env["ir.model"].search(
            [("model", "=", "res.partner")], limit=1
        )
        self.bridge.model_id = partner_model
        with self.assertRaisesRegex(UserError, "must not be restricted"):
            self.task.action_openwebui_draft_description()

    def test_missing_model_and_ambiguous_bridge_are_reported(self):
        self.bridge.openwebui_model = False
        with self.assertRaises(ValidationError):
            self.task.action_openwebui_draft_description()

        self.bridge.openwebui_model = "test-model"
        self.bridge.copy({"name": "Duplicate task description bridge"})
        with self.assertRaisesRegex(UserError, "exactly one active"):
            self.task.action_openwebui_draft_description()

    def test_external_users_cannot_request_task_drafts(self):
        portal_user = new_test_user(
            self.env, login="task-description-portal", groups="base.group_portal"
        )
        with self.assertRaises(AccessError):
            self.task.with_user(portal_user).action_openwebui_draft_description()
