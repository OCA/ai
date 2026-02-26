from unittest import mock

from odoo.tests import HttpCase, tagged

from odoo.addons.ai_oca_native_llm.tests.common import OllamaMockResponse


@tagged("post_install", "-at_install")
class TestAiThreadTour(HttpCase):
    @mock.patch("odoo.addons.ai_oca_native_llm.models.ai_llm_client.Client")
    def test_ai_thread_tour(self, mock_client_class):
        mock_instance = mock_client_class.return_value
        mock_instance.chat.return_value = OllamaMockResponse("Hello from mock")

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

        self.start_tour(
            f"/odoo/action-{custom_action.id}", "ai_thread_tour", login="admin"
        )

        mock_instance.chat.assert_called_with(
            model="llama3",
            messages=mock.ANY,
            options=None,
            stream=False,
        )

        # Verify the custom logic partially instead of the whole blob
        call_args = mock_instance.chat.call_args_list[-1][1]
        system_message = call_args["messages"][0]["content"]

        self.assertIn(
            "The contextual record name is 'Test Tour Partner 1'.", system_message
        )
        self.assertIn('"name": "Test Tour Partner 1"', system_message)
