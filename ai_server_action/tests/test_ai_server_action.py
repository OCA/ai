# Copyright 2026 Dixmit
# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo_test_helper import FakeModelLoader

from odoo.tests.common import TransactionCase


class TestAiServerAction(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.loader = FakeModelLoader(cls.env, cls.__module__)
        cls.loader.backup_registry()
        from .fake_models import AiConnection

        cls.loader.update_registry((AiConnection,))
        cls.addClassCleanup(cls.loader.restore_registry)

        cls.partner_model = cls.env["ir.model"].search(
            [("model", "=", "res.partner")], limit=1
        )
        cls.connection = cls.env["ai.connection"].create(
            {
                "name": "Demo Connection",
                "kind": "demo",
            }
        )
        cls.partner = cls.env["res.partner"].create({"name": "Test Partner"})

    def _create_action(self, output_mode="none"):
        return self.env["ir.actions.server"].create(
            {
                "name": "Test AI Action",
                "model_id": self.partner_model.id,
                "state": "ai_oca",
                "ai_connection_id": self.connection.id,
                "ai_prompt": "Say hello",
                "ai_output_mode": output_mode,
            }
        )

    def test_action_state_added(self):
        states = self.env["ir.actions.server"].fields_get(["state"])
        self.assertTrue(any(s[0] == "ai_oca" for s in states["state"]["selection"]))

    def test_action_post_message(self):
        action = self._create_action("post_message")
        messages = self.partner.message_ids
        action.with_context(active_id=self.partner.id, active_model="res.partner").run()
        new_msgs = self.partner.message_ids - messages
        self.assertEqual(len(new_msgs), 1)
        self.assertIn("demo response to the prompt", new_msgs.body)

    def test_action_update_record(self):
        field = self.env["ir.model.fields"].search(
            [("model_id", "=", self.partner_model.id), ("name", "=", "comment")],
            limit=1,
        )
        action = self._create_action("update_record")
        action.ai_update_record_field_id = field.id
        action.with_context(active_id=self.partner.id, active_model="res.partner").run()
        self.assertIn("demo response", self.partner.comment)

    def test_action_none(self):
        action = self._create_action("none")
        result = action.with_context(
            active_id=self.partner.id, active_model="res.partner"
        ).run()
        # None mode runs without error, returns False
        self.assertFalse(result)

    def test_action_store_variable(self):
        action = self._create_action("store_variable")
        action.ai_context_variable = "ai_result"
        action._run_action_ai_oca({"record": self.partner})
        # Variable stored in eval_context for programmatic use
