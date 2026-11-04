# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged

from odoo.addons.mail_message_import.tests.common import UNKNOWN_ADDRESS

from .common import AiMessageImportCase


@tagged("post_install", "-at_install")
class TestDashboard(AiMessageImportCase):
    """The panel and the records show the documents found by the AI."""

    def _card(self):
        self.channel.invalidate_recordset()
        return self.channel

    def test_card_counts_what_waits(self):
        self._receive("Hola", sender=UNKNOWN_ADDRESS)
        self._receive("Te paso el presupuesto")
        card = self._card()
        self.assertEqual(card.document_count, 0)
        self.assertEqual(card.review_count, 0)
        self.assertEqual(card.new_count, 0)

    def test_links_open_the_documents(self):
        message = self._receive("Te paso el presupuesto")
        for action in (
            self.channel.action_view_documents(),
            self.channel.action_view_review(),
            self.channel.action_view_new(),
        ):
            self.assertEqual(action["res_model"], "ai.message.import.document")
            self.assertIn(("channel_id", "in", self.channel.ids), action["domain"])
        self.assertTrue(self.channel.action_view_review()["context"])
        action = self.sender.action_view_documents()
        self.assertIn(("sender_id", "in", self.sender.ids), action["domain"])
        self.assertEqual(self.sender.document_count, 0)
        action = message.action_view_documents()
        self.assertEqual(action["domain"], [("id", "in", [])])
        self.assertEqual(message.document_count, 0)
        conversation = message.conversation_id
        action = conversation.action_view_documents()
        self.assertEqual(action["domain"], [("conversation_id", "=", conversation.id)])
        self.assertEqual(conversation.document_count, 0)

    def test_learned_records_take_the_sender_of_the_company(self):
        Sender = self.env["mail.message.import.sender"]
        self.assertEqual(Sender._single_of_company(), self.sender)
        unit = self.env.ref("uom.product_uom_unit")
        mapping = self.env["ai.message.import.uom.mapping"].create(
            {"uom_text": "Caja de kilo", "uom_id": unit.id}
        )
        self.assertEqual(
            (mapping.sender_id, mapping.key), (self.sender, "caja de kilo")
        )
        Sender.create({"name": "Second sender"})
        self.assertFalse(Sender._single_of_company())
