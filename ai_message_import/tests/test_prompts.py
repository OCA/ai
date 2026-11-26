# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import tagged

from ..services.ai_client import AIError
from ..services.prompts import fill_placeholders
from .common import AiMessageImportCase

TYPES = {"sale": {"label": "Customer order (sale)"}}


@tagged("post_install", "-at_install")
class TestPrompts(AiMessageImportCase):
    """The text of the prompts is data: the module only assembles it."""

    def _types(self):
        Quote = type(self.env["ai.message.import.document"])
        return patch.object(Quote, "_document_types", lambda self: TYPES)

    def test_prompts_are_assembled(self):
        Prompt = self.env["ai.message.import.prompt"]
        Prompt.search(
            [("code", "=", "extraction")]
        ).content = "Read.\n{types}\nv{version}"
        Prompt.search(
            [("code", "=", "document_type.sale")]
        ).content = "An order of\n a customer."
        self._receive("Pedido")
        with self._types(), self._ai(self._answer()) as calls:
            self._process()
        self.assertTrue(calls.instructions[0].startswith("Read.\n"))
        self.assertIn('- "sale": An order of a customer.', calls.instructions[0])
        self.assertNotIn("{version}", calls.instructions[0])

    def test_missing_prompt(self):
        with self.assertRaises(AIError) as error:
            self.env["ai.message.import.prompt"]._content("nothing")
        self.assertFalse(error.exception.retryable)
        self.assertIn("nothing", str(error.exception))

    def test_conversation_without_prompt_is_an_incident(self):
        self.env["ai.message.import.prompt"].search(
            [("code", "=", "document_type.sale")]
        ).unlink()
        conversation = self._receive("Pedido").conversation_id
        with self._types(), self._ai(self._answer()) as calls:
            self._process()
        self.assertFalse(calls, "Nothing goes to the AI without its prompt")
        self.assertEqual(conversation.state, "error")
        self.assertFalse(conversation.next_attempt_date, "Retrying would not help")
        self.assertIn("document_type.sale", conversation.incident_ids.description)

    def test_the_module_creates_its_prompts_without_text(self):
        extraction = self.env.ref("ai_message_import.prompt_extraction")
        self.assertEqual(extraction.code, "extraction")
        choice = self.env.ref("ai_message_import.prompt_product_choice")
        self.assertEqual(choice.code, "product_choice")
        Prompt = self.env["ai.message.import.prompt"]
        self.assertIn("extraction", Prompt._required_codes())
        self.assertFalse(Prompt.create({"name": "Empty", "code": "empty"}).content)

    def test_missing_prompts_are_warned(self):
        self.assertFalse(self.config.missing_prompts)
        self.env.ref("ai_message_import.prompt_extraction").content = False
        self.env.ref("ai_message_import.prompt_product_choice").content = " "
        self.config.invalidate_recordset(["missing_prompts"])
        self.assertEqual(self.config.missing_prompts, "extraction, product_choice")
        # Without the choice of products, its prompt is not needed.
        self.config.ai_product_choice = False
        self.assertEqual(self.config.missing_prompts, "extraction")
        action = self.config.action_open_prompts()
        self.assertEqual(action["res_model"], "ai.message.import.prompt")

    def test_placeholders(self):
        self.assertEqual(fill_placeholders("{a} {b} {c}", a=1, b="x"), "1 x {c}")
