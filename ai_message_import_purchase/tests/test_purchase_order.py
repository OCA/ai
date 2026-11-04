# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tools.misc import formatLang

from odoo.addons.mail_message_import.tests.common import CLIENT_ADDRESS

from .common import AiMessagePurchaseCase


@tagged("post_install", "-at_install")
class TestPurchaseOrder(AiMessagePurchaseCase):
    # ------------------------------------------------------------------
    # Vendor
    # ------------------------------------------------------------------

    def test_vendor_found_by_vat(self):
        quote = self._run(
            self._quote([self._line("Tornillo", 10, product_code="FN-100")])
        )
        order = quote.purchase_order_id
        self.assertEqual(quote.state, "done")
        self.assertEqual(quote.partner_match_method, "vat")
        self.assertEqual(order.partner_id, self.vendor)
        self.assertEqual(order.state, "draft")
        self.assertEqual(order.partner_ref, "P-2026-001")
        self.assertEqual(order.currency_id, self.currency)
        self.assertEqual(order.ai_message_import_sender_id, self.sender)

    def test_buyer_of_the_vendor(self):
        buyer = new_test_user(
            self.env,
            login="ai_message_vendor_buyer",
            groups="purchase.group_purchase_user",
        )
        self.vendor.buyer_id = buyer
        quote = self._run(
            self._quote([self._line("Tornillo", 10, product_code="FN-100")])
        )
        self.assertEqual(quote.purchase_order_id.user_id, buyer)

    def test_reliable_vendor_is_created(self):
        quote = self._run(
            self._quote(
                [self._line("Glue", 10, product_code="GLU-500")],
                partner={
                    "name": "Maderas Levante SL",
                    "vat": "B99999997",
                    "email": "info@maderas.example",
                    "confidence": 0.95,
                },
            )
        )
        vendor = quote.purchase_order_id.partner_id
        self.assertEqual(vendor.name, "Maderas Levante SL")
        self.assertEqual(vendor.company_id, self.company)
        self.assertEqual(vendor.supplier_rank, 1)
        self.assertEqual(quote.partner_match_method, "created")

    def test_uncertain_vendor_waits_for_a_person(self):
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                partner={"name": "Some shop", "confidence": 0.4},
            )
        )
        self.assertEqual(quote.state, "pending")
        self.assertFalse(quote.purchase_order_id)
        self.assertEqual(self._incident_types(quote), {"partner"})
        self.assertTrue(quote.message_ids, "The messages are kept")
        # A person selects the vendor and applies the quote again.
        quote.partner_id = self.vendor
        self.assertEqual(quote.partner_match_method, "manual")
        quote.action_apply()
        self.assertEqual(quote.state, "done")
        self.assertEqual(quote.purchase_order_id.partner_id, self.vendor)
        self.assertFalse(self._incident_types(quote))

    def test_buttons_and_panel_of_the_document(self):
        card = self.channel
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                partner={"name": "Some shop", "confidence": 0.4},
            )
        )
        incident = quote.incident_ids
        self.assertEqual(quote.open_incident_count, 1)
        self.assertIn(incident.name, quote.open_incident_summary)
        # A single incident opens straight on its form.
        action = quote.action_view_incidents()
        self.assertEqual(action["res_model"], incident._name)
        self.assertEqual(action["res_id"], incident.id)
        self.assertEqual(quote.message_count, len(quote.message_ids))
        self.assertEqual(quote.action_view_batch()["res_id"], quote.conversation_id.id)
        self.assertEqual(
            incident.action_open_conversation()["res_id"], quote.conversation_id.id
        )
        card.invalidate_recordset()
        self.assertEqual((card.review_count, card.new_count), (1, 1))
        self.assertEqual(card.purchase_to_confirm_count, 0)
        graph = json.loads(card.dashboard_graph)[0]
        self.assertFalse(graph["is_sample_data"])
        self.assertEqual(graph["values"][-1]["value"], 1, "Received today")
        # Solved, the document has its order, ready to be confirmed.
        quote.partner_id = self.vendor
        quote.action_apply()
        self.assertFalse(quote.open_incident_count)
        self.assertFalse(quote.open_incident_summary)
        card.invalidate_recordset()
        self.assertEqual(card.review_count, 0)
        self.assertEqual(card.purchase_to_confirm_count, 1)
        action = card.action_view_purchases_to_confirm()
        orders = self.env["purchase.order"].search(action["domain"])
        self.assertEqual(orders, quote.purchase_order_id)

    def test_product_added_by_hand_is_used(self):
        Mapping = self.env["ai.message.import.product.mapping"]
        mapping = Mapping.create(
            {
                "sender_id": self.sender.id,
                "partner_id": self.vendor.id,
                "key_type": "code",
                "partner_text": "XY-77",
                "product_id": self.product_glue.id,
            }
        )
        self.assertEqual((mapping.key, mapping.source), ("xy77", "user"))
        with self.assertRaises(ValidationError):
            Mapping.create(
                {
                    "sender_id": self.sender.id,
                    "partner_id": self.vendor.id,
                    "key_type": "code",
                    "partner_text": "--",
                    "product_id": self.product_glue.id,
                }
            )
        quote = self._run(
            self._quote([self._line("Pegamento", 3, product_code="xy 77")])
        )
        self.assertEqual(quote.line_ids.product_id, self.product_glue)
        self.assertEqual(quote.line_ids.product_match, "mapping")
        self.assertEqual(mapping.usage_count, 0, "Counted when learned, not used")

    def test_order_tells_where_its_document_came_from(self):
        quote = self._run(
            self._quote([self._line("Tornillo", 10, product_code="FN-100")])
        )
        order = quote.purchase_order_id
        self.assertEqual(quote.channel_id, self.channel)
        self.assertEqual(quote.authorized_address_id.address, CLIENT_ADDRESS)
        self.assertEqual(order.ai_message_import_address, CLIENT_ADDRESS)
        self.assertEqual(order.ai_message_import_origin, quote.origin_display)
        self.assertIn(CLIENT_ADDRESS, order.ai_message_import_origin)
        incident = self.env["mail.message.import.incident"].search(
            [("conversation_id", "=", quote.conversation_id.id)], limit=1
        )
        if incident:
            self.assertEqual(incident.origin_display, quote.origin_display)

    def test_document_is_new_until_each_person_opens_it(self):
        quote = self._run(
            self._quote([self._line("Tornillo", 10, product_code="FN-100")])
        )
        ana, luis = (
            new_test_user(
                self.env,
                login=login,
                groups="mail_message_import.group_mail_message_import_manager,"
                "purchase.group_purchase_user",
            )
            for login in ("ai_message_ana", "ai_message_luis")
        )
        Quote = self.env["ai.message.import.document"].with_user(ana)
        self.assertTrue(quote.with_user(ana).is_new)
        self.assertIn(quote, Quote.search([("is_new", "=", True)]))
        quote.with_user(ana).action_mark_seen()
        quote.invalidate_recordset()
        self.assertFalse(quote.with_user(ana).is_new)
        self.assertNotIn(quote, Quote.search([("is_new", "=", True)]))
        self.assertIn(quote, Quote.search([("is_new", "=", False)]))
        # Still new for whoever has not opened it.
        self.assertTrue(quote.with_user(luis).is_new)
        quote.with_user(luis).action_mark_seen()
        self.assertEqual(quote.seen_user_ids, ana | luis)

    def test_order_is_created_when_the_vendor_is_set(self):
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                partner={"name": "Some shop", "confidence": 0.4},
            )
        )
        self.assertFalse(quote.purchase_order_id)
        # No "Apply again": choosing the vendor creates the order.
        quote.partner_id = self.vendor
        self.assertEqual(quote.state, "done")
        self.assertEqual(quote.purchase_order_id.partner_id, self.vendor)
        self.assertFalse(self._incident_types(quote))

    def test_order_is_created_when_the_blocking_incident_is_resolved(self):
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="SCR-M6")],
                partner={"name": "Some shop", "confidence": 0.4},
            )
        )
        incident = quote.incident_ids
        # The vendor is created in Odoo, then the incident is resolved.
        self.env["res.partner"].create(
            {"name": "Some shop", "is_company": True, "supplier_rank": 1}
        )
        incident.action_resolve()
        self.assertEqual(quote.state, "done")
        self.assertEqual(quote.purchase_order_id.partner_id.name, "Some shop")

    def test_dismissed_incident_creates_nothing(self):
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                partner={"name": "Some shop", "confidence": 0.4},
            )
        )
        quote.incident_ids.action_dismiss()
        self.assertEqual(quote.state, "pending")
        self.assertFalse(quote.purchase_order_id)

    def test_line_is_added_when_its_product_is_set(self):
        quote = self._run(
            self._quote(
                [
                    self._line("Tornillo", 10, product_code="FN-100"),
                    self._line("Pieza rara", 3, product_code="ZZ-999"),
                ]
            )
        )
        order = quote.purchase_order_id
        pending = quote.line_ids.filtered(lambda line: line.state == "pending")
        self.assertEqual(len(order.order_line), 1)
        pending.product_id = self.product_glue
        self.assertEqual(pending.state, "applied")
        self.assertEqual(
            order.order_line.product_id, self.product_screw | self.product_glue
        )

    def test_review_incident_resolved_is_not_raised_again(self):
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100", price_unit=15)],
                totals={"untaxed": 150, "total": 181.5},
            )
        )
        reviews = quote.incident_ids.filtered(lambda i: i.state == "open")
        reviews.action_resolve()
        self.assertFalse(self._incident_types(quote))

    def test_same_name_with_another_vat_is_another_vendor(self):
        quote = self._run(
            self._quote(
                [self._line("Glue", 2, product_code="GLU-500")],
                partner={
                    "name": "Ferreteria Norte SL",
                    "vat": "B87878781",
                    "confidence": 0.95,
                },
            )
        )
        self.assertNotEqual(quote.purchase_order_id.partner_id, self.vendor)
        self.assertEqual(quote.partner_match_method, "created")

    def test_client_is_never_the_vendor(self):
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                partner={
                    "name": "Acme Client SL",
                    "vat": "B11111119",
                    "confidence": 0.99,
                },
            )
        )
        self.assertFalse(quote.purchase_order_id)
        self.assertEqual(self._incident_types(quote), {"partner"})
        self.assertFalse(
            self.env["res.partner"].search([("vat", "=", "B11111119")]),
            "The sender must not be created as a vendor either",
        )

    # ------------------------------------------------------------------
    # Products and prices
    # ------------------------------------------------------------------

    def test_odoo_vendor_price_prevails(self):
        quote = self._run(
            self._quote(
                [self._line("Tornillo M6", 10, product_code="FN-100", price_unit=10.0)]
            )
        )
        line = quote.purchase_order_id.order_line
        self.assertEqual(line.product_id, self.product_screw)
        self.assertEqual(quote.line_ids.product_match, "supplier_code")
        self.assertEqual(line.product_qty, 10, "The quantity comes from the document")
        self.assertEqual(line.price_unit, 12.0, "The vendor price of Odoo prevails")
        self.assertIn("Odoo price (vendor price list)", quote.processing_notes)
        notes = quote.purchase_order_id.message_ids.filtered(
            lambda m: m.subtype_id == self.env.ref("mail.mt_note")
        )
        self.assertIn("quoted price", notes[0].body)
        self.assertNotIn(quote.name, quote.purchase_order_id.notes or "")
        # The price list of the vendor is not touched.
        self.assertEqual(self.product_screw.seller_ids.price, 12.0)

    def _order_note(self, quote):
        return quote.purchase_order_id.message_ids.filtered(
            lambda m: m.subtype_id == self.env.ref("mail.mt_note")
        )

    def _agent(self):
        """A user that acts for the module, as a module may set one
        (``mail.message.import.config._agent_user``)."""
        agent = self.env["res.users"].create(
            {
                "name": "Agent",
                "login": "ai-message-agent",
                "company_id": self.company.id,
                "company_ids": [(6, 0, self.company.ids)],
            }
        )
        patcher = patch.object(self.Config, "_agent_user", return_value=agent)
        patcher.start()
        self.addCleanup(patcher.stop)
        # The chatter messages of the creation are checked too.
        self.env = self.env(
            context=dict(self.env.context, tracking_disable=False, mail_notrack=False)
        )
        return agent

    def _chatter_authors(self, records):
        return (
            self.env["mail.message"]
            .search([("model", "=", records._name), ("res_id", "in", records.ids)])
            .author_id
        )

    def test_agent_does_everything(self):
        agent = self._agent()
        quote = self._run(
            self._quote([self._line("Tornillo M6", 10, product_code="FN-100")])
        )
        order = quote.purchase_order_id
        self.assertEqual(quote.conversation_id.message_ids.create_uid, agent)
        self.assertEqual(quote.conversation_id.create_uid, agent)
        self.assertEqual(quote.create_uid, agent)
        self.assertEqual(order.create_uid, agent)
        self.assertEqual(self._chatter_authors(quote), agent.partner_id)
        self.assertEqual(self._chatter_authors(order), agent.partner_id)
        self.assertEqual(self._order_note(quote).author_id, agent.partner_id)

    def test_agent_marks_the_duplicates(self):
        agent = self._agent()
        lines = [self._line("Tornillo M6", 10, product_code="FN-100")]
        first = self._run(self._quote(lines))
        # The same quote number again.
        again = self._run(self._quote(lines))
        self.assertEqual(again.state, "duplicate")
        self.assertEqual(again.duplicate_of_id, first)
        self.assertEqual(again.incident_ids.create_uid, agent)
        self.assertEqual(self._chatter_authors(again), agent.partner_id)
        self.assertEqual(self._chatter_authors(again.incident_ids), agent.partner_id)

    def test_odoobot_without_agent(self):
        root = self.env.ref("base.user_root")
        with patch.object(
            self.Config, "_agent_user", return_value=self.env["res.users"]
        ):
            quote = self._run(
                self._quote([self._line("Tornillo M6", 10, product_code="FN-100")])
            )
        self.assertEqual(quote.purchase_order_id.create_uid, root)
        self.assertEqual(self._order_note(quote).author_id, root.partner_id)

    def test_a_person_keeps_what_she_does(self):
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                partner={"name": "Some shop", "confidence": 0.4},
            )
        )
        buyer = self.env["res.users"].create(
            {
                "name": "Buyer",
                "login": "wpg-buyer",
                "groups_id": [
                    (4, self.env.ref("purchase.group_purchase_user").id),
                    (
                        4,
                        self.env.ref(
                            "mail_message_import.group_mail_message_import_manager"
                        ).id,
                    ),
                ],
            }
        )
        quote.with_user(buyer).partner_id = self.vendor
        quote.with_user(buyer).action_apply()
        self.assertEqual(quote.purchase_order_id.create_uid, buyer)

    def test_cost_used_without_vendor_price(self):
        quote = self._run(
            self._quote([self._line("Glue", 4, product_code="GLU-500", price_unit=6.0)])
        )
        line = quote.purchase_order_id.order_line
        self.assertEqual(line.product_id, self.product_glue)
        self.assertEqual(line.price_unit, 5.0)
        self.assertIn("Odoo price (product cost)", quote.processing_notes)
        self.assertEqual(
            self.product_glue.standard_price, 5.0, "The cost is not changed"
        )

    def test_zero_cost_is_flagged(self):
        quote = self._run(
            self._quote([self._line("Brush", 2, product_code="BRU-01", price_unit=3.0)])
        )
        line = quote.purchase_order_id.order_line
        self.assertEqual(line.price_unit, 0.0)
        self.assertIn("price_zero", self._incident_types(quote))

    def test_unknown_product_is_created(self):
        quote = self._run(
            self._quote(
                [
                    self._line(
                        "Cinta americana 50mm", 6, product_code="CA-50", price_unit=4.5
                    )
                ]
            )
        )
        line = quote.purchase_order_id.order_line
        product = line.product_id
        self.assertEqual(product.name, "Cinta americana 50mm")
        self.assertEqual(product.type, "consu", "Goods are created as goods")
        self.assertEqual(product.company_id, self.company)
        self.assertEqual(product.standard_price, 4.5)
        self.assertEqual(line.price_unit, 4.5, "A new product takes the quoted price")
        self.assertEqual(quote.line_ids.product_match, "created")
        mapping = self.env["ai.message.import.product.mapping"].search(
            [("product_id", "=", product.id)]
        )
        self.assertEqual(mapping.sender_id, self.sender)
        self.assertEqual(mapping.partner_id, self.vendor)

    def test_product_chosen_by_ai_before_creating_one(self):
        message = self._receive("presupuesto")
        answer = self._answer(
            self._quote([self._line("Screww M6", 100, price_unit=0.5)])
        )
        choice = {
            "lines": [
                {
                    "line": 1,
                    "product": self.product_screw.id,
                    "confidence": 0.9,
                    "reason": "Tornillo M6.",
                }
            ]
        }
        with self._ai(answer, choice) as calls:
            self._process()
        quote = message.conversation_id.document_ids
        self.assertIn("vendor", calls.instructions[1])
        self.assertEqual(quote.line_ids.product_id, self.product_screw)
        self.assertEqual(quote.line_ids.product_match, "ai")
        order = quote.purchase_order_id
        self.assertEqual(order.order_line.product_id, self.product_screw)
        order.button_confirm()
        mapping = self.env["ai.message.import.product.mapping"].search(
            [("product_id", "=", self.product_screw.id)]
        )
        self.assertEqual(mapping.source, "ai")
        self.assertEqual(mapping.partner_id, self.vendor)

    def test_products_proposed_while_the_vendor_is_unknown(self):
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="SCR-M6")],
                partner={"name": "Ferreteria desconocida", "confidence": 0.9},
            )
        )
        self.assertEqual(quote.state, "pending")
        self.assertEqual(self._incident_types(quote), {"partner"})
        self.assertEqual(quote.line_ids.product_id, self.product_screw)
        self.assertEqual(quote.line_ids.product_match, "internal_reference")

    def _purchase_tax(self, name, scope, group):
        return self.env["account.tax"].create(
            {
                "name": name,
                "amount": 21,
                "type_tax_use": "purchase",
                "tax_scope": scope,
                "tax_group_id": group.id,
                "company_id": self.company.id,
            }
        )

    def _goods_and_service_taxes(self):
        """A default tax for goods and its only twin for services."""
        group = self.env["account.tax.group"].create(
            {"name": "WPG VAT 21%", "company_id": self.company.id}
        )
        goods = self._purchase_tax("WPG 21% goods", "consu", group)
        service = self._purchase_tax("WPG 21% services", "service", group)
        self.company.account_purchase_tax_id = goods
        return goods, service

    def test_service_line_creates_a_service(self):
        _goods, service_tax = self._goods_and_service_taxes()
        quote = self._run(
            self._quote(
                [
                    self._line(
                        "Mantenimiento anual de la web",
                        1,
                        price_unit=300.0,
                        is_service=True,
                    )
                ]
            )
        )
        product = quote.purchase_order_id.order_line.product_id
        self.assertTrue(quote.line_ids.is_service)
        self.assertEqual(product.type, "service")
        self.assertEqual(product.supplier_taxes_id, service_tax)
        self.assertIn("Service Mantenimiento anual", quote.processing_notes)

    def test_hours_create_a_service(self):
        self._goods_and_service_taxes()
        quote = self._run(
            self._quote(
                [self._line("Consultoría Odoo", 5, uom="Hora(s)", price_unit=60.0)]
            )
        )
        line = quote.purchase_order_id.order_line
        self.assertFalse(quote.line_ids.is_service, "The AI did not say it")
        self.assertEqual(line.product_id.type, "service", "Quoted in hours")
        self.assertEqual(line.product_uom, self.env.ref("uom.product_uom_hour"))
        self.assertEqual(line.product_qty, 5)

    def test_service_keeps_the_default_tax_without_a_single_twin(self):
        goods, service_tax = self._goods_and_service_taxes()
        self._purchase_tax("WPG 21% services bis", "service", service_tax.tax_group_id)
        quote = self._run(
            self._quote([self._line("Soporte", 1, price_unit=50.0, is_service=True)])
        )
        product = quote.purchase_order_id.order_line.product_id
        self.assertEqual(product.type, "service")
        self.assertEqual(product.supplier_taxes_id, goods)

    def test_product_creation_can_be_disabled(self):
        self.config.auto_create_product = False
        quote = self._run(
            self._quote(
                [
                    self._line("Tornillo", 10, product_code="FN-100"),
                    self._line("Cinta", 6, product_code="CA-50", price_unit=4.5),
                ]
            )
        )
        self.assertEqual(len(quote.purchase_order_id.order_line), 1)
        self.assertIn("product", self._incident_types(quote))

    def test_partial_order(self):
        quote = self._run(
            self._quote(
                [
                    self._line("Tornillo", 10, product_code="FN-100"),
                    self._line("Glue", 2, product_code="GLU-500"),
                    self._line("Nails", 3, product_code="NAI-30", uom="palé"),
                ]
            )
        )
        order = quote.purchase_order_id
        self.assertEqual(
            order.order_line.product_id, self.product_screw | self.product_glue
        )
        incident = quote.incident_ids.filtered(lambda i: i.incident_type == "uom")
        self.assertEqual(incident.purchase_order_id, order)
        self.assertEqual(incident.document_line_id.state, "pending")
        self.assertIn("palé", incident.original_values)

    # ------------------------------------------------------------------
    # Units
    # ------------------------------------------------------------------

    def test_unit_conversion(self):
        quote = self._run(
            self._quote([self._line("Glue", 2, product_code="GLU-500", uom="docenas")])
        )
        line = quote.purchase_order_id.order_line
        self.assertEqual(line.product_qty, 24)
        self.assertEqual(line.product_uom, self.uom_unit)
        self.assertIn("conversion factor 12", quote.processing_notes)

    def test_packaging_conversion(self):
        quote = self._run(
            self._quote(
                [
                    self._line(
                        "Clavo 30",
                        5,
                        product_code="NAI-30",
                        uom="cajas",
                        price_unit=2.4,
                    )
                ]
            )
        )
        line = quote.purchase_order_id.order_line
        self.assertEqual(line.product_qty, 120, "5 boxes of 24 units")
        self.assertEqual(line.product_packaging_id, self.packaging_box)
        self.assertEqual(line.price_unit, 0.1)
        # 2.4 per box is 0.10 per unit: no price difference.
        self.assertNotIn("quoted price", quote.processing_notes)

    def test_packaging_quantity_must_match(self):
        quote = self._run(
            self._quote(
                [
                    self._line("Tornillo", 10, product_code="FN-100"),
                    self._line("Clavo 30", 5, product_code="NAI-30", uom="cajas de 6"),
                ]
            )
        )
        self.assertEqual(
            quote.purchase_order_id.order_line.product_id, self.product_screw
        )
        self.assertIn("uom", self._incident_types(quote))

    def test_incompatible_unit_is_pending(self):
        quote = self._run(
            self._quote(
                [
                    self._line("Tornillo", 10, product_code="FN-100"),
                    self._line("Glue", 3, product_code="GLU-500", uom="kg"),
                ]
            )
        )
        self.assertEqual(len(quote.purchase_order_id.order_line), 1)
        self.assertIn("uom", self._incident_types(quote))

    # ------------------------------------------------------------------
    # Discounts
    # ------------------------------------------------------------------

    def test_line_discount(self):
        quote = self._run(
            self._quote(
                [
                    self._line(
                        "Tornillo",
                        10,
                        product_code="FN-100",
                        price_unit=12,
                        discount_percent=10,
                    )
                ]
            )
        )
        line = quote.purchase_order_id.order_line
        self.assertEqual(line.price_unit, 12.0)
        self.assertEqual(line.discount, 10.0)

    def test_global_discount_percent(self):
        quote = self._run(
            self._quote(
                [
                    self._line(
                        "Tornillo",
                        10,
                        product_code="FN-100",
                        price_unit=12,
                        discount_percent=10,
                    ),
                    self._line("Glue", 4, product_code="GLU-500", price_unit=5),
                ],
                global_discount={"percent": 5},
            )
        )
        lines = quote.purchase_order_id.order_line
        screw = lines.filtered(lambda ln: ln.product_id == self.product_screw)
        glue = lines.filtered(lambda ln: ln.product_id == self.product_glue)
        self.assertAlmostEqual(screw.discount, 14.5, places=2)
        self.assertAlmostEqual(glue.discount, 5.0, places=2)
        self.assertIn("Global discount of the document", quote.processing_notes)

    def test_global_discount_amount(self):
        quote = self._run(
            self._quote(
                [self._line("Glue", 20, product_code="GLU-500", price_unit=5)],
                global_discount={"amount": 10},
            )
        )
        self.assertAlmostEqual(
            quote.purchase_order_id.order_line.discount, 10.0, places=2
        )

    def test_uncertain_global_discount_is_not_applied(self):
        quote = self._run(
            self._quote(
                [self._line("Glue", 20, product_code="GLU-500", price_unit=5)],
                global_discount={"percent": 5, "amount": 50},
            )
        )
        self.assertEqual(quote.purchase_order_id.order_line.discount, 0.0)
        self.assertIn("discount", self._incident_types(quote))

    # ------------------------------------------------------------------
    # Taxes and currency
    # ------------------------------------------------------------------

    def test_missing_tax_is_not_exempt(self):
        self.product_glue.supplier_taxes_id = False
        quote = self._run(
            self._quote([self._line("Glue", 2, product_code="GLU-500", tax_percent=21)])
        )
        self.assertFalse(quote.purchase_order_id.order_line.taxes_id)
        incident = quote.incident_ids.filtered(
            lambda i: i.incident_type == "tax_missing"
        )
        self.assertIn("NOT considered exempt", incident.description)

    def test_tax_difference_keeps_odoo_taxes(self):
        quote = self._run(
            self._quote([self._line("Glue", 2, product_code="GLU-500", tax_percent=10)])
        )
        self.assertEqual(quote.purchase_order_id.order_line.taxes_id, self.tax_21)
        self.assertIn("tax_difference", self._incident_types(quote))

    def test_foreign_currency_is_converted(self):
        foreign = self._foreign_currency()
        self.env["res.currency.rate"].create(
            {
                "currency_id": foreign.id,
                "rate": 0.5,
                "name": fields.Date.today() - timedelta(days=1),
                "company_id": self.company.id,
            }
        )
        quote = self._run(
            self._quote(
                [self._line("Cinta", 2, product_code="CA-50", price_unit=10.0)],
                currency=foreign.name,
            )
        )
        order = quote.purchase_order_id
        self.assertEqual(
            order.currency_id, self.currency, "Orders use the company currency"
        )
        self.assertAlmostEqual(order.order_line.price_unit, 20.0, places=2)
        self.assertIn(
            f"Exchange rate: 1 {foreign.name} = 2.000000", quote.processing_notes
        )

    def test_currency_without_rate(self):
        foreign = self._foreign_currency()
        quote = self._run(
            self._quote(
                [
                    self._line("Tornillo", 10, product_code="FN-100", price_unit=9),
                    self._line("Cinta", 2, product_code="CA-50", price_unit=10.0),
                ],
                currency=foreign.name,
            )
        )
        order = quote.purchase_order_id
        self.assertEqual(order.order_line.product_id, self.product_screw)
        self.assertEqual(order.order_line.price_unit, 12.0)
        self.assertTrue({"currency", "product"} <= self._incident_types(quote))

    # ------------------------------------------------------------------
    # Transport, dates, terms, address, totals
    # ------------------------------------------------------------------

    def test_transport_line(self):
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                shipping={"amount": 15.0, "description": "Portes"},
            )
        )
        freight = quote.purchase_order_id.order_line.filtered(
            lambda ln: ln.ai_message_import_line_kind == "freight"
        )
        self.assertEqual(freight.product_id, self.freight)
        self.assertEqual(freight.price_unit, 15.0)
        self.assertEqual(freight.taxes_id, self.tax_21)

    def test_transport_without_product_is_pending(self):
        self.config.freight_product_id = False
        Product = self.env["product.product"]
        transports = Product.search([("name", "ilike", "transport")])
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                shipping={"amount": 15.0},
            )
        )
        self.assertEqual(len(quote.purchase_order_id.order_line), 1)
        self.assertIn("freight", self._incident_types(quote))
        self.assertFalse(
            Product.search([("name", "ilike", "transport")]) - transports,
            "No freight product is created",
        )

    def test_quoted_delivery_date(self):
        date = fields.Date.today() + timedelta(days=10)
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                delivery={"date": fields.Date.to_string(date)},
            )
        )
        self.assertEqual(quote.purchase_order_id.order_line.date_planned.date(), date)

    def test_delivery_date_computed_by_odoo(self):
        self.product_screw.seller_ids.delay = 7
        quote = self._run(
            self._quote([self._line("Tornillo", 10, product_code="FN-100")])
        )
        line = quote.purchase_order_id.order_line
        self.assertEqual(
            line.date_planned.date(),
            (quote.purchase_order_id.date_order + timedelta(days=7)).date(),
        )
        self.assertIn("Odoo planned it", quote.processing_notes)

    def test_past_line_delivery_date(self):
        past = fields.Date.today() - timedelta(days=30)
        quote = self._run(
            self._quote(
                [
                    self._line(
                        "Tornillo",
                        10,
                        product_code="FN-100",
                        delivery_date=fields.Date.to_string(past),
                    )
                ]
            )
        )
        line = quote.purchase_order_id.order_line
        self.assertNotEqual(line.date_planned.date(), past)
        self.assertIn("delivery_date", self._incident_types(quote))

    def test_ambiguous_delivery_date(self):
        date = fields.Date.today() + timedelta(days=10)
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                delivery={
                    "date": fields.Date.to_string(date),
                    "date_is_ambiguous": True,
                },
            )
        )
        self.assertNotEqual(
            quote.purchase_order_id.order_line.date_planned.date(), date
        )
        self.assertIn("delivery_date", self._incident_types(quote))

    def test_quoted_payment_terms(self):
        term_45 = self.env.ref("account.account_payment_term_45days")
        self.vendor.property_supplier_payment_term_id = term_45
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                payment_terms={"text": "Pago a 30 días", "days": 30},
            )
        )
        order = quote.purchase_order_id
        self.assertEqual(
            order.payment_term_id, self.env.ref("account.account_payment_term_30days")
        )
        self.assertIn("45 Days", quote.processing_notes)

    def test_payment_terms_without_equivalent(self):
        term_45 = self.env.ref("account.account_payment_term_45days")
        self.vendor.property_supplier_payment_term_id = term_45
        count = self.env["account.payment.term"].search_count([])
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                payment_terms={"text": "37 días", "days": 37},
            )
        )
        self.assertEqual(quote.purchase_order_id.payment_term_id, term_45)
        self.assertIn("payment_term", self._incident_types(quote))
        self.assertEqual(self.env["account.payment.term"].search_count([]), count)

    def test_delivery_to_a_warehouse(self):
        warehouse = self.env["stock.warehouse"].create(
            {"name": "Almacen Valencia", "code": "VAL"}
        )
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                delivery={"address": "Entregar en Almacén Valencia, muelle 3"},
            )
        )
        self.assertEqual(quote.purchase_order_id.picking_type_id, warehouse.in_type_id)

    def test_unknown_delivery_address(self):
        default_type = (
            self.env["purchase.order"]
            .with_company(self.company)
            ._default_picking_type()
        )
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                delivery={"address": "Calle Inventada 99, Cuenca"},
            )
        )
        self.assertEqual(quote.purchase_order_id.picking_type_id, default_type)
        self.assertIn("delivery_address", self._incident_types(quote))

    def test_total_difference(self):
        quote = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100", price_unit=10)],
                totals={"untaxed": 100.0, "total": 121.0},
            )
        )
        order = quote.purchase_order_id
        self.assertEqual(
            order.amount_untaxed, 120.0, "Prices are not adapted to the total"
        )
        incident = quote.incident_ids.filtered(
            lambda i: i.incident_type == "total_difference"
        )
        self.assertIn("prices of Odoo differ", incident.description)
        self.assertEqual(incident.category, "review")

    def _price_cause(self, quote, amount):
        incident = quote.incident_ids.filtered(
            lambda i: i.incident_type == "total_difference"
        )
        cause = "the prices of Odoo differ from the quoted ones by " + formatLang(
            self.env, amount, currency_obj=self.currency
        )
        self.assertIn(cause, incident.description)

    def test_small_unit_difference_of_a_converted_line(self):
        # 143.90 per dozen is 11.9917 per unit, 0.0083 less than the price of
        # Odoo: nothing per unit, 1.00 for the 120 units of the line.
        quote = self._run(
            self._quote(
                [
                    self._line(
                        "Tornillo",
                        10,
                        product_code="FN-100",
                        uom="docenas",
                        price_unit=143.9,
                    )
                ],
                totals={"untaxed": 1439.0, "total": 1741.19},
            )
        )
        line = quote.purchase_order_id.order_line
        self.assertEqual(line.product_qty, 120)
        self.assertEqual(line.price_unit, 12.0)
        self.assertIn("quoted price", quote.processing_notes)
        self._price_cause(quote, 1.0)

    def test_price_difference_with_line_discount(self):
        quote = self._run(
            self._quote(
                [
                    self._line(
                        "Tornillo",
                        10,
                        product_code="FN-100",
                        price_unit=10.0,
                        discount_percent=10.0,
                    )
                ],
                totals={"untaxed": 90.0, "total": 108.9},
            )
        )
        line = quote.purchase_order_id.order_line
        self.assertEqual(line.discount, 10.0)
        self.assertEqual(line.price_subtotal, 108.0)
        # (12 - 10) x 10 units, less the 10% discount of the line: 18, not 20.
        self._price_cause(quote, 18.0)

    def test_matching_totals_raise_nothing(self):
        quote = self._run(
            self._quote(
                [
                    self._line(
                        "Tornillo",
                        10,
                        product_code="FN-100",
                        price_unit=12,
                        tax_percent=21,
                    )
                ],
                totals={"untaxed": 120.0, "tax": 25.2, "total": 145.2},
            )
        )
        self.assertFalse(self._incident_types(quote))

    def test_source_documents_on_the_order(self):
        message = self._receive(
            files=[
                {
                    "name": "presupuesto.pdf",
                    "raw": b"%PDF-1.4 document",
                    "mimetype": "application/pdf",
                }
            ]
        )
        answer = self._answer(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                document_refs=["D1"],
            )
        )
        with self._ai(answer) as calls:
            self._process()
        self.assertEqual(calls[0][2]["mimetype"], "application/pdf")
        order = message.conversation_id.document_ids.purchase_order_id
        self.assertIn(
            "presupuesto.pdf", order.message_ids.attachment_ids.mapped("name")
        )
