from unittest.mock import patch

from odoo.tests.common import TransactionCase

from odoo.addons.ai_server_action.models import ir_actions_server


class TestAiServerAction(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_model = cls.env["ir.model"].search(
            [("model", "=", "res.partner")], limit=1
        )
        cls.partner = cls.env["res.partner"].create({"name": "Test Partner"})

    def _create_action(self, output_mode="none"):
        return self.env["ir.actions.server"].create(
            {
                "name": "Test AI Action",
                "model_id": self.partner_model.id,
                "state": "ai_oca",
                "ai_prompt": "Say hello",
                "ai_output_mode": output_mode,
            }
        )

    def _run_action_with_mock(self, action):
        """Execute action with _run patched on the ai.connection model."""
        with patch(
            "odoo.addons.ai_connection.models.ai_connection.AiConnection._run",
            return_value=("This is a mocked response", 10, 5, 1),
        ):
            return action.with_context(
                active_id=self.partner.id, active_model="res.partner"
            ).run()

    def test_action_state_added(self):
        states = self.env["ir.actions.server"].fields_get(["state"])
        self.assertTrue(any(s[0] == "ai_oca" for s in states["state"]["selection"]))

    def test_mailing_model_real(self):
        action = self._create_action()
        self.assertEqual(action.mailing_model_real, "res.partner")
        action_without_model = self.env["ir.actions.server"].new(
            {"name": "Test AI Action", "state": "ai_oca"}
        )
        self.assertFalse(action_without_model.mailing_model_real)

    def test_get_ai_oca_prompt_without_record(self):
        action = self._create_action()
        self.assertEqual(action._get_ai_oca_prompt(None), "Say hello")

    def test_get_ai_oca_prompt_with_record(self):
        action = self._create_action()
        action.ai_prompt = "<p>Hello <t t-out='object.name'/></p>"
        self.assertEqual(action._get_ai_oca_prompt(self.partner), "Hello Test Partner")

    def test_action_post_message(self):
        action = self._create_action("post_message")
        messages = self.partner.message_ids
        self._run_action_with_mock(action)
        new_msgs = self.partner.message_ids - messages
        self.assertEqual(len(new_msgs), 1)
        self.assertIn("mocked response", new_msgs.body)

    def test_action_post_message_with_markdown(self):
        action = self._create_action("post_message")
        messages = self.partner.message_ids
        with patch.object(ir_actions_server, "markdown") as mock_markdown:
            mock_markdown.markdown.side_effect = lambda text: f"<p>{text}</p>"
            self._run_action_with_mock(action)
        new_msgs = self.partner.message_ids - messages
        self.assertEqual(len(new_msgs), 1)
        self.assertIn("<p>", new_msgs.body)
        self.assertIn("mocked response", new_msgs.body)

    def test_action_update_record(self):
        field = self.env["ir.model.fields"].search(
            [("model_id", "=", self.partner_model.id), ("name", "=", "comment")],
            limit=1,
        )
        action = self._create_action("update_record")
        action.ai_update_record_field_id = field.id
        self._run_action_with_mock(action)
        self.assertIn("mocked response", self.partner.comment)

    def test_action_update_record_html_with_markdown(self):
        field = self.env["ir.model.fields"].search(
            [("model_id", "=", self.partner_model.id), ("name", "=", "comment")],
            limit=1,
        )
        self.assertEqual(field.ttype, "html")
        action = self._create_action("update_record")
        action.ai_update_record_field_id = field.id
        with patch.object(ir_actions_server, "markdown") as mock_markdown:
            mock_markdown.markdown.side_effect = lambda text: f"<p>{text}</p>"
            self._run_action_with_mock(action)
        self.assertIn("<p>", self.partner.comment)
        self.assertIn("mocked response", self.partner.comment)

    def test_action_none(self):
        action = self._create_action("none")
        self._run_action_with_mock(action)

    def test_action_store_variable(self):
        action = self._create_action("store_variable")
        action.ai_context_variable = "ai_result"
        eval_context = {"record": self.partner}
        with patch(
            "odoo.addons.ai_connection.models.ai_connection.AiConnection._run",
            return_value=("This is a mocked response", 10, 5, 1),
        ):
            action._run_action_ai_oca(eval_context)
        self.assertEqual(eval_context["ai_result"], "This is a mocked response")

    def test_action_store_variable_without_variable(self):
        action = self._create_action("store_variable")
        eval_context = {"record": self.partner}
        with patch(
            "odoo.addons.ai_connection.models.ai_connection.AiConnection._run",
            return_value=("This is a mocked response", 10, 5, 1),
        ):
            action._run_action_ai_oca(eval_context)
        self.assertNotIn("ai_result", eval_context)
