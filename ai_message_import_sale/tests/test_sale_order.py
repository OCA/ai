# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
from datetime import timedelta
from email.message import EmailMessage
from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import Form, new_test_user, tagged

from odoo.addons.ai_message_import.services.ai_client import AIError
from odoo.addons.ai_message_import.services.matching import PartnerMatcher
from odoo.addons.ai_message_import.services.tools import AUTOMATION_CONTEXT_KEY

from .common import AiMessageSaleCase


@tagged("post_install", "-at_install")
class TestSaleOrder(AiMessageSaleCase):
    def _first_order(self):
        quote = self._run(
            self._order(
                [
                    self._line("Azulejo blanco", 40, product_code="AZ-2020"),
                    self._line("Cemento cola", 10, product_code="CEM-25"),
                ]
            )
        )
        return quote, quote.sale_order_id

    # ------------------------------------------------------------------
    # Quotation
    # ------------------------------------------------------------------

    def test_panel_counts_the_quotations_to_confirm(self):
        quote, order = self._first_order()
        self.channel.invalidate_recordset()
        self.assertEqual(self.channel.sale_to_confirm_count, 1)
        action = self.channel.action_view_sales_to_confirm()
        self.assertEqual(self.env["sale.order"].search(action["domain"]), order)
        self.assertEqual(quote.action_view_order()["res_id"], order.id)

    def test_customer_order_creates_a_quotation(self):
        quote, order = self._first_order()
        self.assertEqual(quote.state, "done")
        self.assertEqual(quote.document_type, "sale")
        self.assertEqual(quote.partner_match_method, "vat")
        self.assertEqual(order._name, "sale.order")
        self.assertEqual(order.state, "draft")
        self.assertEqual(order.partner_id, self.customer)
        self.assertEqual(order.client_order_ref, "PED-778")
        self.assertEqual(order.pricelist_id, self.pricelist)
        self.assertEqual(order.currency_id, self.currency)
        self.assertEqual(order.ai_message_import_sender_id, self.sender)
        self.assertEqual(order.origin, quote.name)
        tile = order.order_line.filtered(lambda ln: ln.product_id == self.product_tile)
        cement = order.order_line.filtered(
            lambda ln: ln.product_id == self.product_cement
        )
        self.assertEqual(tile.product_uom_qty, 40)
        self.assertEqual(tile.price_unit, 9.0, "Price of the price list")
        self.assertEqual(cement.price_unit, 8.5, "Sales price of the product")
        self.assertEqual(tile.tax_id, self.tax_21)
        self.assertEqual(tile.ai_message_import_document_line_id, quote.line_ids[0])
        self.assertEqual(quote.line_ids[0].sale_line_id, tile)
        self.assertFalse(self._incident_types(quote))
        self.assertTrue(order.message_ids.filtered(lambda m: quote.name in m.body))
        self.assertEqual(quote.change_ids[:1].sale_order_id, order)

    def test_salesperson_of_the_customer(self):
        salesperson = new_test_user(
            self.env,
            login="ai_message_salesperson",
            groups="sales_team.group_sale_salesman",
        )
        self.customer.user_id = salesperson
        quote = self._run(
            self._order([self._line("Azulejo", 5, product_code="AZ-2020")])
        )
        self.assertEqual(quote.sale_order_id.user_id, salesperson)

    def test_the_module_creates_the_prompt_of_its_type(self):
        prompt = self.env.ref("ai_message_import_sale.prompt_document_type_sale")
        self.assertEqual(prompt.code, "document_type.sale")
        self.assertIn(
            "document_type.sale", self.env["ai.message.import.prompt"]._required_codes()
        )

    def test_ai_chooses_the_type_of_each_document(self):
        self.company.vat = "ESB46719084"
        message = self._receive("Pedido de la obra")
        answer = self._answer(
            self._order([self._line("Azulejo", 5, product_code="AZ-2020")])
        )
        with self._ai(answer) as calls:
            self._process()
        instructions, schema = calls.instructions[0], calls.schemas[0]
        description = " ".join(
            self.env["ai.message.import.prompt"]._content("document_type.sale").split()
        )
        self.assertIn(f'- "sale": {description}', instructions)
        item = schema["properties"]["quotes"]["items"]["properties"]
        self.assertIn("sale", item["document_type"]["enum"])
        request = calls[0][0]["text"]
        self.assertIn(
            f"Company of the sender (never the partner of a document): "
            f"{self.company.name} (VAT ESB46719084)",
            request,
        )
        quote = message.conversation_id.document_ids
        self.assertEqual(quote.document_type, "sale")
        self.assertTrue(quote.sale_order_id)

    def test_document_of_no_known_type(self):
        message = self._receive(
            files=[
                {
                    "name": "nomina.pdf",
                    "raw": b"%PDF-1.4 payslip",
                    "mimetype": "application/pdf",
                }
            ]
        )
        notes = "D1 is a payslip, not a commercial document."
        with self._ai(self._answer(notes=notes)):
            self._process()
        conversation = message.conversation_id
        self.assertFalse(conversation.document_ids)
        incident = conversation.incident_ids
        self.assertEqual(incident.incident_type, "no_document")
        self.assertIn("Customer order (sale)", incident.description)
        self.assertIn(notes, incident.description)

    def test_quoted_price_differs_from_the_price_list(self):
        quote = self._run(
            self._order(
                [self._line("Azulejo", 10, product_code="AZ-2020", price_unit=10.0)]
            )
        )
        order = quote.sale_order_id
        self.assertEqual(order.order_line.price_unit, 9.0)
        self.assertIn("price list Professional customers", quote.processing_notes)

    def test_zero_price_is_flagged(self):
        quote = self._run(
            self._order([self._line("Muestra", 1, product_code="MUE-01")])
        )
        self.assertTrue(quote.sale_order_id)
        self.assertIn("price_zero", self._incident_types(quote))

    def test_packaging_is_converted(self):
        quote = self._run(
            self._order(
                [self._line("Azulejo", 4, product_code="AZ-2020", uom="Caja 10")]
            )
        )
        line = quote.sale_order_id.order_line
        self.assertEqual(line.product_uom_qty, 40)
        self.assertEqual(line.product_packaging_id, self.packaging_box)

    # ------------------------------------------------------------------
    # Products and customers
    # ------------------------------------------------------------------

    def test_names_written_without_accents(self):
        skirting = self._create_product("Rodapié porcelánico 60x8 cm gris", "", 2.75)
        customer = self.env["res.partner"].create(
            {"name": "Cerámicas Martínez SL", "is_company": True, "customer_rank": 1}
        )
        quote = self._run(
            self._order(
                [self._line("Rodapie porcelanico 60x8 cm, gris", 40)],
                partner={"name": "Ceramicas Martinez", "confidence": 0.9},
                quote_number=False,
            )
        )
        self.assertEqual(quote.partner_id, customer)
        self.assertEqual(quote.partner_match_method, "name")
        self.assertEqual(quote.line_ids.product_id, skirting)
        self.assertEqual(quote.line_ids.product_match, "name")
        self.assertEqual(quote.sale_order_id.order_line.product_uom_qty, 40)

    # ------------------------------------------------------------------
    # Real orders: forwarded emails, aliases, codes of the customers
    # ------------------------------------------------------------------

    def test_forwarded_email_is_unpacked(self):
        mail = EmailMessage()
        mail["From"] = "Pedidos <pedidos@company.example>"
        mail["Subject"] = "RV: Pedido compra 1026-AL0796"
        mail.set_content("De: compras@levante.example\nAsunto: Pedido 1026-AL0796")
        mail.add_attachment(
            b"%PDF-1.7 order of the customer",
            maintype="application",
            subtype="pdf",
            filename="Pedido 1026-AL0796.pdf",
        )
        message = self._receive(
            files=[
                {
                    "name": "RV Pedido compra 1026-AL0796.msg",
                    "raw": mail.as_bytes(),
                    "mimetype": "application/octet-stream",
                }
            ]
        )
        answer = self._answer(
            self._order(
                [self._line("Azulejo", 10, product_code="AZ-2020")],
                quote_number="1026-AL0796",
                partner={
                    "name": "Construcciones Levante",
                    "email": "compras@levante.example",
                    "confidence": 0.9,
                },
            )
        )
        with self._ai(answer) as calls:
            self._process()
        names = message.attachment_ids.mapped("name")
        self.assertIn(
            "RV Pedido compra 1026-AL0796.msg / Pedido 1026-AL0796.pdf", names
        )
        parts = calls[0]
        self.assertTrue(
            any(p.get("mimetype") == "application/pdf" for p in parts),
            "The PDF inside the email goes to the AI",
        )
        self.assertTrue(
            any("De: compras@levante.example" in p.get("text", "") for p in parts),
            "The email goes as text",
        )
        quote = message.conversation_id.document_ids
        self.assertEqual(quote.sale_order_id.partner_id, self.customer)
        # Unpacked once.
        message.conversation_id._unpack_emails(message)
        self.assertEqual(message.attachment_ids.mapped("name"), names)

    def test_customer_alias_is_learned(self):
        quote = self._run(
            self._order(
                [self._line("Azulejo", 5, product_code="AZ-2020")],
                partner={"name": "fruveicod", "confidence": 0.8},
                quote_number=False,
            )
        )
        self.assertEqual(self._incident_types(quote), {"partner"})
        quote.partner_id = self.customer
        quote.action_apply()
        self.assertEqual(quote.sale_order_id.partner_id, self.customer)
        again = self._run(
            self._order(
                [self._line("Azulejo", 8, product_code="AZ-2020")],
                partner={"name": "FRUVEICOD", "confidence": 0.8},
                quote_number=False,
            ),
            text="fruveicod 8 azulejos",
        )
        self.assertEqual(again.partner_id, self.customer)
        self.assertEqual(again.partner_match_method, "mapping")
        self.assertTrue(again.sale_order_id)

    def test_contact_and_unit_added_by_hand_are_used(self):
        self.env["ai.message.import.partner.mapping"].create(
            {
                "sender_id": self.sender.id,
                "partner_text": "Fruveicod",
                "partner_id": self.customer.id,
            }
        )
        self.env["ai.message.import.uom.mapping"].create(
            {
                "sender_id": self.sender.id,
                "uom_text": "Saco",
                "uom_id": self.env.ref("uom.product_uom_unit").id,
            }
        )
        quote = self._run(
            self._order(
                [self._line("Cemento cola", 6, product_code="CEM-25", uom="saco")],
                partner={"name": "FRUVEICOD", "confidence": 0.8},
                quote_number=False,
            )
        )
        self.assertEqual(quote.partner_id, self.customer)
        self.assertEqual(quote.partner_match_method, "mapping")
        self.assertNotIn("uom", self._incident_types(quote))
        self.assertEqual(quote.sale_order_id.order_line.product_uom_qty, 6)

    def test_units_of_a_box_are_ordered_as_boxes(self):
        # Odoo sells the box of 144; the customer counts the units in it.
        flautas = self._create_product(
            "Flautas de pollo cong 40-45 grs aprox144", "08.06.0023", 69.336
        )
        quote = self._run(
            self._order(
                [
                    self._line(
                        "FLAUTA DE POLLO 40-45GR [UD]",
                        288,
                        product_code="08.06.0023",
                        uom="UD",
                        price_unit=0.481,
                    )
                ]
            )
        )
        line = quote.sale_order_id.order_line
        self.assertEqual(line.product_id, flautas)
        self.assertEqual(line.product_uom_qty, 2)
        self.assertAlmostEqual(line.price_unit, 69.336, places=2)
        self.assertIn("144", quote.processing_notes)
        self.assertNotIn("pack_size", self._incident_types(quote))

    def test_units_that_fill_no_whole_box_are_checked(self):
        self._create_product(
            "Flautas de jamon y queso 40 gr144 unds", "08.06.0024", 72.6
        )
        quote = self._run(
            self._order(
                [
                    self._line(
                        "Flauta jamon y queso",
                        300,
                        product_code="08.06.0024",
                        uom="uds",
                        price_unit=0.5,
                    )
                ]
            )
        )
        self.assertAlmostEqual(
            quote.sale_order_id.order_line.product_uom_qty, 300 / 144, places=2
        )
        self.assertIn("pack_size", self._incident_types(quote))

    def test_units_per_box_written_in_the_line(self):
        self._create_product("Flautas de jamon y queso", "FL-JQ", 35.412)
        quote = self._run(
            self._order(
                [
                    self._line(
                        "FLAUTA JAMON Y QUESO 50GR 78U/C [UD]",
                        156,
                        product_code="FL-JQ",
                        uom="UD",
                        price_unit=0.454,
                    )
                ]
            )
        )
        self.assertEqual(quote.sale_order_id.order_line.product_uom_qty, 2)

    def test_box_price_alone_does_not_convert(self):
        # The quoted price matches no content of the product: Odoo decides it.
        quote = self._run(
            self._order(
                [self._line("Cemento cola", 4, product_code="CEM-25", price_unit=50)]
            )
        )
        self.assertEqual(quote.sale_order_id.order_line.product_uom_qty, 4)

    def test_customer_by_internal_reference(self):
        self.customer.ref = "CLI-0042"
        quote = self._run(
            self._order(
                [self._line("Azulejo", 5, product_code="AZ-2020")],
                partner={"name": "cli 0042", "confidence": 0.8},
                quote_number=False,
            )
        )
        self.assertEqual(quote.partner_id, self.customer)
        self.assertEqual(quote.partner_match_method, "ref")

    def _trade_name(self):
        """``function`` stands for the trade name of l10n_es_partner."""
        return patch.object(PartnerMatcher, "trade_name_field", "function")

    def _partner_reason(self, quote):
        return quote.incident_ids.filtered(
            lambda i: i.incident_type == "partner"
        ).description

    def test_customer_by_trade_name(self):
        customer = self.env["res.partner"].create(
            {
                "name": "Javier Domínguez Pimentel",
                "function": "FRUVEICOD",
                "customer_rank": 1,
            }
        )
        with self._trade_name():
            quote = self._run(
                self._order(
                    [self._line("Azulejo", 5, product_code="AZ-2020")],
                    partner={"name": "fruveicod", "confidence": 0.9},
                    quote_number=False,
                )
            )
        self.assertEqual(quote.partner_id, customer)
        self.assertEqual(quote.partner_match_method, "name")
        self.assertTrue(quote.sale_order_id)

    def test_customer_name_written_apart(self):
        customer = self.env["res.partner"].create(
            {"name": "GUSTOPIZZA", "customer_rank": 1}
        )
        quote = self._run(
            self._order(
                [self._line("Azulejo", 5, product_code="AZ-2020")],
                partner={"name": "Gusto pizza", "confidence": 0.9},
                quote_number=False,
            )
        )
        self.assertEqual(quote.partner_id, customer)
        self.assertEqual(quote.partner_match_method, "name")

    def test_customer_by_part_of_the_name(self):
        customer = self.env["res.partner"].create(
            {
                "name": "Elzbieta Kaszibiak",
                "function": "Cafetería Samoga",
                "customer_rank": 1,
            }
        )
        with self._trade_name():
            quote = self._run(
                self._order(
                    [self._line("Azulejo", 5, product_code="AZ-2020")],
                    partner={"name": "SAMOGA", "confidence": 0.9},
                    quote_number=False,
                )
            )
        self.assertEqual(quote.partner_id, customer)
        self.assertEqual(quote.partner_match_method, "name_part")

    def test_part_of_the_name_does_not_choose(self):
        self.env["res.partner"].create(
            [
                {"name": "Cafetería Samoga", "customer_rank": 1},
                {"name": "Samoga Eventos SL"},
            ]
        )
        quote = self._run(
            self._order(
                [self._line("Azulejo", 5, product_code="AZ-2020")],
                partner={"name": "Samoga", "confidence": 0.9},
                quote_number=False,
            )
        )
        self.assertFalse(quote.partner_id)
        self.assertEqual(self._incident_types(quote), {"partner"})
        self.assertIn("Several partners", self._partner_reason(quote))

    # ------------------------------------------------------------------
    # Products chosen by the AI
    # ------------------------------------------------------------------

    def _lettuce(self):
        bags = self._create_product("CANONIGOS BOLSA FLO 500 grs/2", "ZE13846", 6.4)
        trays = self._create_product("CANONIGOS FLORETTE 125 GRS/8", "ZE5345", 7.1)
        return bags, trays

    def _sold(self, product):
        """A confirmed order of the customer with ``product``."""
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "company_id": self.company.id,
                "order_line": [
                    Command.create({"product_id": product.id, "product_uom_qty": 3})
                ],
            }
        )
        order.action_confirm()

    def _choice(self, product, confidence=0.93):
        return {
            "lines": [
                {
                    "line": 1,
                    "product": product.id,
                    "confidence": confidence,
                    "reason": "Bolsas de 500 g.",
                }
            ]
        }

    def _run_choosing(self, line, choice, text="kilo canonicos"):
        """Process an order of ``line``; the AI answers ``choice`` when it is
        asked for the products. :return: the quote and the calls to the AI."""
        message = self._receive(text)
        answer = self._answer(self._order([line], quote_number=False))
        with self._ai(answer, choice) as calls:
            self._process()
        return message.conversation_id.document_ids, calls

    def _product_reason(self, quote):
        return quote.incident_ids.filtered(
            lambda i: i.incident_type == "product"
        ).description

    def test_product_chosen_by_ai(self):
        bags, trays = self._lettuce()
        self._sold(bags)
        quote, calls = self._run_choosing(
            self._line("kilo canonicos (2x500 gr)", 2), self._choice(bags)
        )
        self.assertEqual(len(calls), 2, "One more request for the products")
        self.assertIn("customer", calls.instructions[1])
        request = json.loads(calls[1][0]["text"])["lines"][0]
        self.assertEqual(request["text"], "kilo canonicos (2x500 gr)")
        candidates = {c["id"]: c for c in request["candidates"]}
        self.assertEqual(candidates[bags.id]["times_taken"], 1)
        self.assertEqual(candidates[trays.id]["times_taken"], 0)
        self.assertNotIn(self.product_tile.id, candidates)
        self.assertEqual(quote.line_ids.product_id, bags)
        self.assertEqual(quote.line_ids.product_match, "ai")
        order = quote.sale_order_id
        self.assertEqual(order.order_line.product_id, bags)
        self.assertTrue(
            order.message_ids.filtered(lambda m: "chosen by the AI" in str(m.body))
        )
        # Confirmed by a person: learned, the AI is not asked again.
        order.action_confirm()
        mapping = self.env["ai.message.import.product.mapping"].search(
            [("product_id", "=", bags.id)]
        )
        self.assertEqual(mapping.source, "ai")
        again, calls = self._run_choosing(
            self._line("kilo canonicos (2x500 gr)", 4),
            self._choice(trays),
            text="otro pedido",
        )
        self.assertEqual(again.line_ids.product_id, bags)
        self.assertEqual(again.line_ids.product_match, "mapping")
        self.assertEqual(len(calls), 1)

    def test_tokens_of_the_product_choice_are_counted(self):
        bags, _trays = self._lettuce()
        message = self._receive("kilo canonicos")
        line = self._line("kilo canonicos (2x500 gr)", 2)
        answer = self._answer(self._order([line], quote_number=False))
        with self._ai(answer, self._choice(bags), tokens=700):
            self._process()
        self.assertEqual(message.conversation_id.ai_tokens, 1400, "Reading and choice")

    def test_doubtful_choice_of_ai_is_not_used(self):
        bags, trays = self._lettuce()
        quote, _calls = self._run_choosing(
            self._line("canonicos", 2), self._choice(bags, confidence=0.6)
        )
        self.assertFalse(quote.line_ids.product_id)
        self.assertFalse(quote.sale_order_id)
        reason = self._product_reason(quote)
        self.assertIn("The most similar ones", reason)
        self.assertIn(bags.display_name, reason)
        self.assertIn(trays.display_name, reason)

    def test_choice_of_ai_must_be_a_candidate(self):
        self._lettuce()
        quote, _calls = self._run_choosing(
            self._line("kilo canonicos", 2), self._choice(self.product_tile)
        )
        self.assertFalse(quote.line_ids.product_id)
        self.assertEqual(self._incident_types(quote), {"product", "no_document"})

    def test_choice_of_ai_can_be_disabled(self):
        bags, _trays = self._lettuce()
        self.config.ai_product_choice = False
        quote, calls = self._run_choosing(
            self._line("kilo canonicos", 2), self._choice(bags)
        )
        self.assertEqual(len(calls), 1)
        self.assertFalse(quote.line_ids.product_id)
        self.assertIn(bags.display_name, self._product_reason(quote))

    def test_failed_choice_of_ai_leaves_the_line_pending(self):
        self._lettuce()
        quote, _calls = self._run_choosing(
            self._line("kilo canonicos", 2),
            AIError("The AI connection Test AI failed (APIError 503)."),
        )
        self.assertFalse(quote.line_ids.product_id)
        self.assertIn("product", self._incident_types(quote))
        self.assertIn("could not choose the products", quote.processing_notes)

    def test_products_proposed_while_the_customer_is_unknown(self):
        bags, _trays = self._lettuce()
        message = self._receive("pedido de pepe")
        answer = self._answer(
            self._order(
                [
                    self._line("White tile 20x20", 3),
                    self._line("kilo canonicos (2x500 gr)", 2),
                ],
                partner={"name": "Pepe de la obra", "confidence": 0.9},
                quote_number=False,
            )
        )
        with self._ai(answer, self._choice(bags)) as calls:
            self._process()
        quote = message.conversation_id.document_ids
        self.assertEqual(quote.state, "pending")
        self.assertEqual(self._incident_types(quote), {"partner"})
        tile, lettuce = quote.line_ids.sorted("sequence")
        self.assertEqual(tile.product_id, self.product_tile)
        self.assertEqual(tile.product_match, "name")
        self.assertEqual(lettuce.product_id, bags)
        self.assertEqual(lettuce.product_match, "ai")
        request = json.loads(calls[1][0]["text"])["lines"]
        self.assertEqual(len(request), 1, "Only the line without exact match")
        # The customer chosen, its order takes the products already proposed.
        quote.partner_id = self.customer
        quote.action_apply()
        order = quote.sale_order_id
        self.assertEqual(order.order_line.product_id, self.product_tile | bags)
        self.assertTrue(
            order.message_ids.filtered(lambda m: "previous processing" in str(m.body))
        )

    def test_unit_written_as_the_box_abbreviation(self):
        box = self.env["uom.uom"].create(
            {
                "name": "Caja",
                "category_id": self.env.ref("uom.product_uom_categ_unit").id,
                "uom_type": "bigger",
                "factor_inv": 6,
            }
        )
        salad = self._create_product("Ensalada mezclum 500 g", "ZE8864", 9.0)
        salad.write({"uom_id": box.id, "uom_po_id": box.id})
        quote = self._run(
            self._order(
                [self._line("Ensalada mezclum 500 g", 10, uom="c")],
                quote_number=False,
            )
        )
        line = quote.sale_order_id.order_line
        self.assertEqual(line.product_id, salad)
        self.assertEqual(line.product_uom, box)
        self.assertEqual(line.product_uom_qty, 10)

    def test_our_reference_and_barcode(self):
        self.product_cement.barcode = "8412537290052"
        quote = self._run(
            self._order(
                [
                    self._line(
                        "AZULEJO BLANCO",
                        10,
                        product_code="117001071",
                        own_code="AZ-2020",
                    ),
                    self._line(
                        "SW CEMENTO",
                        4,
                        product_code="2602135182",
                        barcode="8412537290052",
                    ),
                ]
            )
        )
        lines = quote.line_ids.sorted("sequence")
        self.assertEqual(lines[0].product_id, self.product_tile)
        self.assertEqual(lines[0].product_match, "internal_reference")
        self.assertEqual(lines[1].product_id, self.product_cement)
        self.assertEqual(lines[1].product_match, "barcode")

    def test_box_abbreviation(self):
        quote = self._run(
            self._order([self._line("Azulejo", 2, product_code="AZ-2020", uom="c")])
        )
        line = quote.sale_order_id.order_line
        self.assertEqual(line.product_uom_qty, 20)
        self.assertEqual(line.product_packaging_id, self.packaging_box)

    def test_unknown_product_is_never_created(self):
        quote = self._run(
            self._order(
                [
                    self._line("Azulejo", 10, product_code="AZ-2020"),
                    self._line(
                        "Grifo monomando", 2, product_code="GR-1", price_unit=45
                    ),
                ]
            )
        )
        self.assertEqual(quote.state, "done")
        self.assertEqual(quote.sale_order_id.order_line.product_id, self.product_tile)
        self.assertIn("product", self._incident_types(quote))
        self.assertEqual(quote.line_ids[1].state, "pending")
        self.assertFalse(
            self.env["product.product"].search([("name", "=", "Grifo monomando")])
        )

    def test_order_without_known_products_creates_nothing(self):
        quote = self._run(
            self._order([self._line("Grifo monomando", 2, product_code="GR-1")])
        )
        self.assertEqual(quote.state, "pending")
        self.assertFalse(quote.sale_order_id)
        self.assertEqual(self._incident_types(quote), {"product", "no_document"})

    def test_chosen_product_is_learned(self):
        quote = self._run(
            self._order([self._line("Adhesivo C2", 3, product_code="X-77")])
        )
        quote.line_ids.product_id = self.product_cement
        quote.action_apply()
        self.assertEqual(quote.state, "done")
        self.assertEqual(quote.sale_order_id.order_line.product_id, self.product_cement)
        again = self._run(
            self._order(
                [self._line("Adhesivo C2", 5, product_code="X-77")],
                quote_number="PED-779",
            )
        )
        self.assertEqual(again.line_ids.product_match, "mapping")
        self.assertEqual(again.sale_order_id.order_line.product_id, self.product_cement)

    # ------------------------------------------------------------------
    # Incidents solved by choosing the record to use
    # ------------------------------------------------------------------

    def _open_incident(self, quote, incident_type):
        return quote.incident_ids.filtered(
            lambda i: i.state == "open" and i.incident_type == incident_type
        )

    def test_product_chosen_on_the_incident_solves_the_same_ones(self):
        first = self._run(
            self._order([self._line("Adhesivo C2", 3, product_code="X-77")])
        )
        second = self._run(
            self._order(
                [self._line("Adhesivo C2", 5, product_code="X-77")],
                quote_number="PED-779",
            ),
            text="Otro pedido",
        )
        incident = self._open_incident(first, "product")
        same = self._open_incident(second, "product")
        self.assertTrue(incident.can_fix and same)
        with self.assertRaises(UserError):
            incident.action_apply_fix()
        incident.fix_product_id = self.product_cement
        incident.action_apply_fix()
        self.assertEqual((incident | same).mapped("state"), ["resolved", "resolved"])
        self.assertEqual(same.fix_product_id, self.product_cement)
        for quote in first | second:
            self.assertEqual(quote.state, "done")
            self.assertFalse(self._incident_types(quote))
            self.assertEqual(
                quote.sale_order_id.order_line.product_id, self.product_cement
            )
        self.assertEqual(first.line_ids.product_match, "manual")
        self.assertEqual(second.line_ids.product_match, "mapping")
        self.assertTrue(
            self.env["ai.message.import.product.mapping"].search(
                [("product_id", "=", self.product_cement.id)]
            )
        )

    def test_unit_chosen_on_the_incident_is_learned(self):
        unit = self.env.ref("uom.product_uom_unit")
        sand = self._create_product("Arena fina", "AR-01", 2.0)
        sand.write(
            {
                "uom_id": self.env.ref("uom.product_uom_kgm").id,
                "uom_po_id": self.env.ref("uom.product_uom_kgm").id,
            }
        )
        first = self._run(
            self._order(
                [
                    self._line("Azulejo", 4, product_code="AZ-2020"),
                    self._line("Cemento cola", 10, product_code="CEM-25", uom="saco"),
                ]
            )
        )
        second = self._run(
            self._order(
                [
                    self._line("Cemento cola", 2, product_code="CEM-25", uom="Saco"),
                    self._line("Arena", 3, product_code="AR-01", uom="saco"),
                ],
                quote_number="PED-780",
            ),
            text="Otro pedido",
        )
        incident = self._open_incident(first, "uom")
        cement, sand_line = self._open_incident(second, "uom").sorted(
            lambda i: i.document_line_id.sequence
        )
        self.assertEqual(incident.line_uom_category_id, unit.category_id)
        incident.fix_uom_id = unit
        incident.action_apply_fix()
        self.assertEqual(incident.state, "resolved")
        self.assertEqual(cement.state, "resolved")
        # A unit of another category does not solve the line of the sand.
        self.assertFalse(sand_line.fix_uom_id)
        self.assertEqual(
            self._open_incident(second, "uom").document_line_id.product_id, sand
        )
        lines = first.sale_order_id.order_line
        self.assertEqual(lines.product_id, self.product_tile | self.product_cement)
        self.assertEqual(
            second.sale_order_id.order_line.filtered(
                lambda line: line.product_id == self.product_cement
            ).product_uom_qty,
            2,
        )
        mapping = self.env["ai.message.import.uom.mapping"].search(
            [("sender_id", "=", first.sender_id.id)]
        )
        self.assertEqual((mapping.key, mapping.uom_id), ("saco", unit))
        # The next documents of the sender know the unit.
        again = self._run(
            self._order(
                [self._line("Cemento cola", 6, product_code="CEM-25", uom="saco")],
                quote_number="PED-781",
            ),
            text="Pedido de cemento",
        )
        self.assertFalse(self._incident_types(again))
        self.assertEqual(again.sale_order_id.order_line.product_uom_qty, 6)
        self.assertIn("as learned for this sender", again.processing_notes)

    def test_unit_set_on_the_quote_line_is_learned(self):
        quote = self._run(
            self._order(
                [self._line("Cemento cola", 10, product_code="CEM-25", uom="saco")]
            )
        )
        self.assertEqual(self._incident_types(quote), {"uom", "no_document"})
        quote.line_ids.uom_id = self.env.ref("uom.product_uom_unit")
        quote.action_apply()
        self.assertEqual(quote.state, "done")
        self.assertTrue(
            self.env["ai.message.import.uom.mapping"].search([("key", "=", "saco")])
        )

    def test_customer_chosen_on_the_incident_solves_the_same_ones(self):
        alias = {"name": "fruveicod", "confidence": 0.8}
        first = self._run(
            self._order(
                [self._line("Azulejo", 5, product_code="AZ-2020")],
                partner=alias,
                quote_number=False,
            )
        )
        second = self._run(
            self._order(
                [self._line("Azulejo", 8, product_code="AZ-2020")],
                partner=dict(alias, name="FRUVEICOD"),
                quote_number=False,
            ),
            text="fruveicod 8 azulejos",
        )
        incident = self._open_incident(first, "partner")
        same = self._open_incident(second, "partner")
        incident.fix_partner_id = self.customer
        incident.action_apply_fix()
        self.assertEqual(same.state, "resolved")
        self.assertEqual(first.partner_match_method, "manual")
        self.assertEqual(second.partner_match_method, "mapping")
        for quote in first | second:
            self.assertEqual(quote.sale_order_id.partner_id, self.customer)

    def test_reliable_customer_is_created(self):
        quote = self._run(
            self._order(
                [self._line("Azulejo", 10, product_code="AZ-2020")],
                partner={
                    "name": "Reformas Ruzafa SL",
                    "vat": "B11111119",
                    "email": "obras@ruzafa.example",
                    "confidence": 0.95,
                },
            )
        )
        customer = quote.sale_order_id.partner_id
        self.assertEqual(customer.name, "Reformas Ruzafa SL")
        self.assertEqual(customer.customer_rank, 1)
        self.assertEqual(customer.company_id, self.company)
        self.assertEqual(quote.partner_match_method, "created")

    def test_customer_without_reliable_data_is_not_created(self):
        quote = self._run(
            self._order(
                [self._line("Azulejo", 10, product_code="AZ-2020")],
                partner={"name": "Pepe de la obra", "confidence": 0.95},
            )
        )
        self.assertEqual(quote.state, "pending")
        self.assertFalse(quote.sale_order_id)
        self.assertEqual(self._incident_types(quote), {"partner"})
        self.assertFalse(
            self.env["res.partner"].search([("name", "=", "Pepe de la obra")])
        )
        reason = self._partner_reason(quote)
        self.assertIn("No customer in Odoo matches", reason)
        self.assertIn("gives no VAT number", reason)
        self.assertIn("remembered for the next time", reason)

    def test_customer_read_with_little_confidence_is_not_created(self):
        quote = self._run(
            self._order(
                [self._line("Azulejo", 10, product_code="AZ-2020")],
                partner={
                    "name": "Reformas Ruzafa SL",
                    "vat": "B11111119",
                    "confidence": 0.5,
                },
            )
        )
        self.assertFalse(quote.partner_id)
        self.assertIn(
            "too little confidence (50%, minimum 80%)", self._partner_reason(quote)
        )

    def test_customer_creation_can_be_disabled(self):
        self.config.auto_create_customer = False
        quote = self._run(
            self._order(
                [self._line("Azulejo", 10, product_code="AZ-2020")],
                partner={
                    "name": "Reformas Ruzafa SL",
                    "vat": "B11111119",
                    "confidence": 0.95,
                },
            )
        )
        self.assertEqual(self._incident_types(quote), {"partner"})
        self.assertIn("disabled in the settings", self._partner_reason(quote))
        quote.partner_id = self.customer
        quote.action_apply()
        self.assertEqual(quote.sale_order_id.partner_id, self.customer)

    def test_sender_is_never_the_customer(self):
        quote = self._run(
            self._order(
                [self._line("Azulejo", 10, product_code="AZ-2020")],
                partner={"name": "Acme Client SL", "confidence": 0.9},
            )
        )
        self.assertEqual(self._incident_types(quote), {"partner"})

    def test_price_list_in_another_currency_is_not_used(self):
        foreign = self._foreign_currency()
        pricelist = self.env["product.pricelist"].create(
            {"name": "Export", "currency_id": foreign.id, "company_id": self.company.id}
        )
        self.customer.with_company(self.company).property_product_pricelist = pricelist
        quote = self._run(
            self._order([self._line("Azulejo", 2, product_code="AZ-2020")])
        )
        order = quote.sale_order_id
        self.assertEqual(order.currency_id, self.currency)
        self.assertFalse(order.pricelist_id)
        self.assertEqual(order.order_line.price_unit, 12.0)
        self.assertIn("currency", self._incident_types(quote))

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------

    def test_delivery_date_and_address(self):
        date = fields.Date.today() + timedelta(days=7)
        quote = self._run(
            self._order(
                [self._line("Azulejo", 10, product_code="AZ-2020")],
                delivery={
                    "date": fields.Date.to_string(date),
                    "address": "Entregar en la obra de Calle Sueca 21, Valencia",
                },
            )
        )
        order = quote.sale_order_id
        self.assertEqual(order.commitment_date.date(), date)
        self.assertEqual(order.partner_shipping_id, self.site)
        self.assertIn(
            "matched to Construcciones Levante SL, Obra Ruzafa", quote.processing_notes
        )
        self.assertFalse(self._incident_types(quote))

    def test_unknown_delivery_address_is_not_created(self):
        quote = self._run(
            self._order(
                [self._line("Azulejo", 10, product_code="AZ-2020")],
                delivery={"address": "Calle Inventada 99, Cuenca"},
            )
        )
        order = quote.sale_order_id
        usual = self.customer.address_get(["delivery"])["delivery"]
        self.assertEqual(order.partner_shipping_id.id, usual)
        self.assertIn("delivery_address", self._incident_types(quote))

    def test_transport_is_added(self):
        quote = self._run(
            self._order(
                [self._line("Azulejo", 10, product_code="AZ-2020")],
                shipping={"amount": 30.0, "description": "Porte"},
            )
        )
        freight = quote.sale_order_id.order_line.filtered(
            lambda ln: ln.ai_message_import_line_kind == "freight"
        )
        self.assertEqual(freight.product_id, self.freight)
        self.assertEqual(freight.price_unit, 30.0)

    # ------------------------------------------------------------------
    # Corrections and confirmation
    # ------------------------------------------------------------------

    def test_correction_updates_the_quotation(self):
        quote, order = self._first_order()
        correction = self._run(
            self._order(
                [
                    self._line("Azulejo blanco", 60, product_code="AZ-2020"),
                    self._line("Cemento cola", 10, product_code="CEM-25"),
                ],
                relation="update",
                target_reference=quote.name,
                relation_reason="The customer wants 60 tiles",
            ),
            text="Corrección",
        )
        self.assertEqual(correction.state, "done")
        self.assertEqual(correction.sale_order_id, order)
        tile = order.order_line.filtered(lambda ln: ln.product_id == self.product_tile)
        self.assertEqual(tile.product_uom_qty, 60)
        self.assertEqual(tile.price_unit, 9.0)
        change = correction.change_ids.filtered(
            lambda c: c.field_name == "product_uom_qty"
        )
        self.assertEqual((change.old_value, change.new_value), ("40.0", "60.0"))
        self.assertEqual(change.sale_order_id, order)

    def test_same_order_again_is_a_duplicate(self):
        quote, order = self._first_order()
        again = self._run(
            self._order(
                [
                    self._line("Azulejo blanco", 40, product_code="AZ-2020"),
                    self._line("Cemento cola", 10, product_code="CEM-25"),
                ]
            ),
            text="Otra vez",
        )
        self.assertEqual(again.state, "duplicate")
        self.assertEqual(again.duplicate_of_id, quote)
        self.assertEqual(
            self.env["sale.order"].search_count(
                [("ai_message_import_sender_id", "=", self.sender.id)]
            ),
            1,
        )

    def test_confirmed_quotation_is_never_modified(self):
        quote, order = self._first_order()
        order.action_confirm()
        correction = self._run(
            self._order(
                [self._line("Azulejo blanco", 99, product_code="AZ-2020")],
                relation="update",
                target_reference=quote.name,
            ),
            text="Corrección",
        )
        self.assertIn("order_locked", self._incident_types(correction))
        self.assertNotIn(99, order.order_line.mapped("product_uom_qty"))

    def test_automation_never_confirms_nor_cancels(self):
        order = self._first_order()[1]
        automated = order.with_context(**{AUTOMATION_CONTEXT_KEY: True})
        with self.assertRaises(UserError):
            automated.action_confirm()
        with self.assertRaises(UserError):
            automated._action_cancel()
        with self.assertRaises(UserError):
            automated.write({"state": "sale"})
        self.assertEqual(order.state, "draft")

    def test_confirmation_warns_about_open_incidents(self):
        quote = self._run(
            self._order([self._line("Muestra", 1, product_code="MUE-01")])
        )
        order = quote.sale_order_id
        self.assertTrue(order.ai_message_import_open_incident_count)
        action = order.action_ai_message_confirm()
        self.assertEqual(action["res_model"], "ai.message.import.order.confirm")
        wizard = Form(
            self.env["ai.message.import.order.confirm"].with_context(
                **action["context"]
            )
        ).save()
        self.assertIn("Zero price", wizard.incident_summary)
        wizard.action_confirm()
        self.assertEqual(order.state, "sale")

    def test_person_removing_a_line_is_respected(self):
        quote, order = self._first_order()
        order.order_line.filtered(
            lambda ln: ln.product_id == self.product_cement
        ).unlink()
        quote.action_apply()
        self.assertEqual(order.order_line.product_id, self.product_tile)
        self.assertIn("human_conflict", self._incident_types(quote))


@tagged("post_install", "-at_install")
class TestMixedDocuments(AiMessageSaleCase):
    """Vendor quotes and customer orders from the same phone."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.purchase_installed = (
            cls.env["ir.module.module"]._get("ai_message_import_purchase").state
            == "installed"
        )
        cls.vendor = cls.env["res.partner"].create(
            {
                "name": "Cerámicas del Turia SL",
                "vat": "ESB99999997",
                "is_company": True,
                "supplier_rank": 1,
            }
        )

    def setUp(self):
        super().setUp()
        if not self.purchase_installed:
            self.skipTest("The purchases of AI Message Import are not installed.")

    def _vendor_quote(self, lines, **values):
        values.setdefault(
            "partner",
            {
                "name": "Cerámicas del Turia S.L.",
                "vat": "B99999997",
                "confidence": 0.9,
            },
        )
        values.setdefault("quote_number", "CT-2026-88")
        values.setdefault("quote_key", "Q2")
        values.setdefault("message_refs", ["M1"])
        values["document_type"] = "purchase"
        return self._quote(lines, **values)

    def test_one_conversation_with_both_types(self):
        quotes = self._run(
            self._order([self._line("Azulejo", 40, product_code="AZ-2020")]),
            self._vendor_quote(
                [self._line("Azulejo", 500, product_code="AZ-2020", price_unit=4.1)]
            ),
        )
        sale_quote = quotes.filtered(lambda q: q.document_type == "sale")
        purchase_quote = quotes.filtered(lambda q: q.document_type == "purchase")
        self.assertEqual(sale_quote.sale_order_id.partner_id, self.customer)
        self.assertFalse(sale_quote.purchase_order_id)
        self.assertEqual(purchase_quote.purchase_order_id.partner_id, self.vendor)
        self.assertFalse(purchase_quote.sale_order_id)
        self.assertEqual(purchase_quote.purchase_order_id.order_line.product_qty, 500)

    def test_type_corrected_by_a_person(self):
        # The AI takes a vendor quote for a customer order.
        quote = self._run(
            self._order(
                [self._line("Azulejo", 500, product_code="AZ-2020", price_unit=4.1)],
                partner={
                    "name": "Cerámicas del Turia S.L.",
                    "vat": "B99999997",
                    "confidence": 0.9,
                },
            )
        )
        order = quote.sale_order_id
        self.assertEqual(order.partner_id, self.vendor)
        with self.assertRaises(UserError):
            quote.document_type = "purchase"
        order.action_cancel()
        quote.document_type = "purchase"
        quote.action_apply()
        self.assertEqual(quote.state, "done")
        self.assertEqual(quote.purchase_order_id.partner_id, self.vendor)

    def test_same_file_of_another_type_is_not_a_duplicate(self):
        first = self._run(
            self._order([self._line("Azulejo", 5, product_code="AZ-2020")])
        )
        self.assertEqual(first.state, "done")
        again = self._run(
            self._vendor_quote(
                [self._line("Azulejo", 5, product_code="AZ-2020", price_unit=4.1)],
                quote_number=first.quote_number,
                partner=first.extraction["partner"],
            ),
            text="Otra vez",
        )
        self.assertNotEqual(again.state, "duplicate")
