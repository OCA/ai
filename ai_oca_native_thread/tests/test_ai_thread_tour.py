from unittest import mock

from odoo.tests import HttpCase, tagged

from odoo.addons.ai_oca_native_llm.tests.common import OpenAIMockResponse


@tagged("post_install", "-at_install")
class TestAiThreadTour(HttpCase):
    @mock.patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.OpenAI")
    def test_ai_thread_tour(self, mock_client_class):
        mock_instance = mock_client_class.return_value
        mock_instance.chat.completions.create.return_value = OpenAIMockResponse(
            "Hello from mock"
        )

        partner1 = self.env["res.partner"].create({"name": "Test Tour Partner 1"})
        partner2 = self.env["res.partner"].create({"name": "Test Tour Partner 2"})

        custom_action = self.env["ir.actions.act_window"].create(
            {
                "name": "Test Contacts",
                "res_model": "res.partner",
                "view_mode": "list,form",
                "domain": [("id", "in", [partner1.id, partner2.id])],
            }
        )

        with mock.patch.object(
            type(self.env["ai.message"]),
            "with_delay",
            new=lambda self_record, **kw: self_record,
        ):
            self.start_tour(
                f"/odoo/action-{custom_action.id}", "ai_thread_tour", login="admin"
            )

        mock_instance.chat.completions.create.assert_called()

        # Verify the model context is present in LLM call messages
        call_args = mock_instance.chat.completions.create.call_args_list[-1][1]
        all_messages_content = " ".join([m["content"] for m in call_args["messages"]])

        self.assertIn("res.partner", all_messages_content)
