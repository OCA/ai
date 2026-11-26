# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.ai_message_import.services.ai_client import AIError
from odoo.addons.ai_message_import.services.tools import AUTOMATION_CONTEXT_KEY

from .common import AiMessagePurchaseCase


@tagged("post_install", "-at_install")
class TestPurchaseCases(AiMessagePurchaseCase):
    """Less frequent cases of the vendor quotes."""

    def _correction(self, quote, lines, **values):
        values.setdefault("relation", "update")
        values.setdefault("target_reference", quote.name)
        values.setdefault("relation_reason", "The vendor corrects the quote")
        return self._run(self._quote(lines, **values), text="Corrección")

    def _incident(self, quote, incident_type):
        return quote.incident_ids.filtered(
            lambda i: i.incident_type == incident_type and i.state == "open"
        )

    # ------------------------------------------------------------------
    # The document and its buttons
    # ------------------------------------------------------------------

    def test_buttons_of_the_document(self):
        quote = self._run(
            self._quote(
                [
                    self._line("Tornillo", 10, product_code="FN-100", tax_percent=10),
                    self._line("Glue", 3, product_code="GLU-500", uom="kg"),
                ]
            )
        )
        self.assertGreater(quote.open_incident_count, 1)
        action = quote.action_view_incidents()
        self.assertEqual(action["domain"], [("id", "in", quote.incident_ids.ids)])
        self.assertEqual(
            quote.action_view_attachments()["domain"],
            [("id", "in", quote.attachment_ids.ids)],
        )
        self.assertEqual(
            quote.action_view_messages()["res_model"], "mail.message.import.message"
        )
        self.assertEqual(
            quote.action_view_changes()["domain"], [("document_id", "=", quote.id)]
        )
        self.assertEqual(
            quote.action_view_duplicates()["res_model"], "ai.message.import.document"
        )
        self.assertIn('"quote_key": "Q1"', quote.extraction_display)
        Document = self.env["ai.message.import.document"]
        self.assertIn(quote, Document.search([("is_new", "=", True)]))
        with self.assertRaises(UserError):
            Document.search([("is_new", "in", [True])])
        with self.assertRaises(UserError):
            Document._document_rules("invoice")
        order = quote.purchase_order_id
        self.assertEqual(
            order.action_ai_message_view_incidents()["domain"][0][2], order.id
        )
        self.assertTrue(order.action_ai_message_view_quotes()["domain"])
        incident = self._incident(quote, "uom")
        self.assertEqual(incident.action_open_order()["res_id"], order.id)
        self.assertEqual(incident.action_open_document()["res_id"], quote.id)

    def test_discarded_document(self):
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                partner={"name": "Some shop", "confidence": 0.4},
            )
        )
        quote.action_discard()
        self.assertEqual(quote.state, "cancelled")
        self.assertEqual(quote.incident_ids.mapped("state"), ["dismissed"])
        with self.assertRaises(UserError):
            quote.action_apply()
        incident = quote.incident_ids
        self.assertFalse(incident.action_open_order())
        incident.action_apply_fix()
        self.assertEqual(incident.state, "dismissed", "Solved ones are skipped")
        incident.state = "open"
        self.assertFalse(incident.can_retry)
        with self.assertRaises(UserError):
            incident.action_retry()

    def test_duplicate_without_order_cannot_correct(self):
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                partner={"name": "Some shop", "confidence": 0.4},
            )
        )
        duplicate = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                partner={"name": "Some shop", "confidence": 0.4},
                relation="duplicate",
                target_reference=quote.name,
                relation_reason="Same PDF sent again",
            ),
            text="Otra vez",
        )
        self.assertEqual(duplicate.state, "duplicate")
        self.assertEqual(duplicate.duplicate_of_id, quote)
        with self.assertRaises(UserError):
            duplicate.action_apply_as_correction()

    def test_lines_corrected_by_a_person(self):
        quote = self._run(self._quote([self._line("Tornillo", 10)]))
        line = quote.line_ids
        line.write({"price_unit": 11.0, "tax_percent": 21.0, "quantity": 0})
        self.assertTrue(line.price_known)
        self.assertTrue(line.tax_known)
        self.assertFalse(line.validation_errors)
        quote.action_apply()
        self.assertIn("invalid_line", self._incident_types(quote))

    def test_without_rights_on_the_orders_the_document_is_only_fixed(self):
        user = self.env["res.users"].create(
            {
                "name": "Reviewer",
                "login": "reviewer",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref(
                                "mail_message_import.group_mail_message_import_manager"
                            ).id,
                        ],
                    )
                ],
            }
        )
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                partner={"name": "Some shop", "confidence": 0.4},
            )
        )
        quote.with_user(user).partner_id = self.vendor
        self.assertFalse(quote.purchase_order_id)

    # ------------------------------------------------------------------
    # Interpretation of the lines
    # ------------------------------------------------------------------

    def test_product_written_by_a_document_without_vendor(self):
        quote = self._run(self._quote([self._line("Pintura roja", 2)]))
        incident = self._incident(quote, "product")
        self.assertTrue(incident._written_key())
        quote.with_context(**{AUTOMATION_CONTEXT_KEY: True}).partner_id = False
        self.assertFalse(incident._written_key())
        self.assertFalse(incident._same_open_incidents(self.product_glue))

    def test_ambiguous_product(self):
        self._create_product("Widget", False, 1.0)
        self._create_product("Widget", False, 2.0)
        quote = self._run(self._quote([self._line("Widget", 1)]))
        incident = self._incident(quote, "product")
        self.assertIn("Several products match", incident.description)

    def test_products_that_cannot_be_created(self):
        quote = self._run(
            self._quote(
                [
                    self._line("Low confidence", 1, price_unit=1.0, confidence=0.1),
                    self._line("", 1, product_code="NEW-1", price_unit=1.0),
                    self._line("Odd unit", 1, uom="furlongs", price_unit=1.0),
                    self._line("Taxed price", 1, price_unit=1.21),
                ],
                prices_include_tax=True,
                currency="",
            )
        )
        reasons = "\n".join(self._incident(quote, "product").mapped("description"))
        self.assertIn("too low", reasons)
        self.assertIn("no description", reasons)
        self.assertIn("furlongs", reasons)
        self.assertIn("unknown rate", reasons)
        self.assertIn("does not state its currency", quote.processing_notes)

    def test_partner_of_a_correction_must_be_the_same(self):
        other = self.env["res.partner"].create(
            {"name": "Otro Proveedor SL", "vat": "ESA28015865", "supplier_rank": 1}
        )
        quote = self._run(
            self._quote([self._line("Tornillo", 10, product_code="FN-100")])
        )
        correction = self._correction(
            quote,
            [self._line("Tornillo", 20, product_code="FN-100")],
            partner={"name": other.name, "vat": other.vat, "confidence": 0.95},
        )
        incident = self._incident(correction, "update_ambiguous")
        self.assertIn("The order was not modified", incident.description)
        self.assertEqual(quote.purchase_order_id.order_line.product_qty, 10)
        self.assertFalse(incident.can_fix)
        with self.assertRaises(UserError):
            incident.action_apply_fix()

    # ------------------------------------------------------------------
    # Transport and totals
    # ------------------------------------------------------------------

    def test_transport_corrected(self):
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                shipping={"amount": 12.1},
                prices_include_tax=True,
            )
        )
        freight = quote.purchase_order_id.order_line.filtered(
            lambda ln: ln.ai_message_import_line_kind == "freight"
        )
        self.assertAlmostEqual(freight.price_unit, 10.0, places=2)
        self._correction(
            quote,
            [self._line("Tornillo", 10, product_code="FN-100")],
            shipping={"amount": 15.0},
        )
        self.assertEqual(freight.price_unit, 15.0)
        freight.price_unit = 18.0
        correction = self._correction(
            quote,
            [self._line("Tornillo", 10, product_code="FN-100")],
            shipping={"amount": 20.0},
        )
        self.assertEqual(freight.price_unit, 18.0, "The price of a person is kept")
        self.assertIn("human_conflict", self._incident_types(correction))

    def test_causes_of_a_total_difference(self):
        foreign = self._foreign_currency()
        self.env["res.currency.rate"].create(
            {
                "currency_id": foreign.id,
                "rate": 1.0,
                "name": fields.Date.today() - timedelta(days=1),
                "company_id": self.company.id,
            }
        )
        self.config.freight_product_id = False
        self.product_glue.supplier_taxes_id = False
        quote = self._run(
            self._quote(
                [
                    self._line("Tornillo", 10, product_code="FN-100", price_unit=12),
                    self._line("Glue", 3, product_code="GLU-500", uom="kg"),
                    self._line("Glue", 2, product_code="GLU-500", tax_percent=21),
                ],
                currency=foreign.name,
                shipping={"amount": 15.0},
                totals={"untaxed": 500.0, "total": 605.0},
            )
        )
        incident = self._incident(quote, "total_difference")
        for cause in (
            "lines pending review",
            "the taxes differ or are missing",
            "the transport charges are pending",
            "currency conversion",
        ):
            self.assertIn(cause, incident.description)

    def test_total_difference_with_a_pending_discount(self):
        quote = self._run(
            self._quote(
                [self._line("Glue", 20, product_code="GLU-500", price_unit=5)],
                global_discount={"percent": 5, "amount": 50},
                totals={"untaxed": 50.0},
            )
        )
        incident = self._incident(quote, "total_difference")
        self.assertIn("the global discount was not applied", incident.description)

    def test_total_difference_without_known_cause(self):
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100", price_unit=12)],
                totals={"untaxed": 130.0},
            )
        )
        incident = self._incident(quote, "total_difference")
        self.assertIn("rounding or data not identified", incident.description)

    # ------------------------------------------------------------------
    # Learned equivalences
    # ------------------------------------------------------------------

    def test_equivalences_need_a_text(self):
        Uom = self.env["ai.message.import.uom.mapping"]
        Partner = self.env["ai.message.import.partner.mapping"]
        with self.assertRaises(ValidationError):
            Uom.create(
                {
                    "sender_id": self.sender.id,
                    "uom_text": "!!",
                    "uom_id": self.uom_kg.id,
                }
            )
        with self.assertRaises(ValidationError):
            Partner.create(
                {
                    "sender_id": self.sender.id,
                    "partner_text": "S.L.",
                    "partner_id": self.vendor.id,
                }
            )
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, uom="cajas")],
                partner={"name": "Some shop", "confidence": 0.4},
            )
        )
        line = quote.line_ids
        Product = self.env["ai.message.import.product.mapping"]
        self.assertFalse(Product._learn(line, self.product_screw), "No partner yet")
        self.assertFalse(Uom._learn(line, False))
        self.assertFalse(Partner._learn(quote, False))
        first = Uom._learn(line, self.uom_dozen)
        self.assertEqual(Uom._learn(line, self.uom_dozen), first)
        self.assertEqual(first.usage_count, 2)
        first = Partner._learn(quote, self.vendor)
        self.assertEqual(Partner._learn(quote, self.vendor), first)
        self.assertEqual(first.usage_count, 2)
        quote.partner_id = self.vendor
        line.write({"description": "", "product_code": False})
        self.assertFalse(Product._learn(line, self.product_screw), "No text")

    # ------------------------------------------------------------------
    # Settings, senders, channels and conversations
    # ------------------------------------------------------------------

    def test_confidences_are_checked(self):
        with self.assertRaises(ValidationError):
            self.config.vendor_min_confidence = 2

    def test_purchases_of_a_sender_and_a_channel(self):
        quote = self._run(
            self._quote([self._line("Tornillo", 10, product_code="FN-100")])
        )
        order = quote.purchase_order_id
        self.sender.invalidate_recordset()
        self.assertEqual(self.sender.purchase_count, 1)
        for record in (self.sender, self.channel):
            action = record.action_view_purchases()
            self.assertEqual(self.env["purchase.order"].search(action["domain"]), order)

    def test_reply_to_a_message_of_a_document(self):
        quote = self._run(
            self._quote([self._line("Tornillo", 10, product_code="FN-100")])
        )
        first = quote.message_ids
        self._receive("Y esto también", reply_to_uid=first.message_uid)
        with self._ai(self._answer()) as calls:
            self._process()
        request = "\n".join(part.get("text", "") for part in calls[0])
        self.assertIn(f"replies to a message of documents: {quote.name}", request)

    def test_failures_of_the_conversation(self):
        Conversation = self.env["mail.message.import.conversation"]
        self.assertEqual(
            Conversation._failure_incident_type(AIError("down")), "ai_error"
        )
        self.assertTrue(Conversation._failure_incident_type(ValueError("other")))
        conversation = self._receive("Presupuesto").conversation_id
        Document = type(self.env["ai.message.import.document"])
        with (
            patch.object(Document, "_document_types", lambda self: {}),
            mute_logger(
                "odoo.addons.mail_message_import.models.mail_message_import_conversation"
            ),
            self._ai(self._answer()),
        ):
            self._process()
        self.assertEqual(conversation.state, "error")
        self.assertIn("No module of document types", conversation.last_error)
        with self.assertRaises(NotImplementedError):
            self.env["ai.message.import.order.mixin"]._ai_message_confirm()
