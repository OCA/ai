# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from odoo.addons.ai_message_import.services.tools import AUTOMATION_CONTEXT_KEY

from .common import AiMessagePurchaseCase


@tagged("post_install", "-at_install")
class TestPurchaseUpdate(AiMessagePurchaseCase):
    def _first_order(self):
        quote = self._run(
            self._quote(
                [
                    self._line("Tornillo", 10, product_code="FN-100"),
                    self._line("Glue", 4, product_code="GLU-500"),
                ]
            )
        )
        return quote, quote.purchase_order_id

    def _correction(self, quote, lines, **values):
        values.setdefault("relation", "update")
        values.setdefault("target_reference", quote.name)
        values.setdefault("relation_reason", "The sender changes the quantity")
        return self._run(self._quote(lines, **values), text="Corrección")

    # ------------------------------------------------------------------
    # Corrections
    # ------------------------------------------------------------------

    def test_correction_updates_the_order(self):
        quote, order = self._first_order()
        correction = self._correction(
            quote,
            [
                self._line("Tornillo", 25, product_code="FN-100"),
                self._line("Glue", 4, product_code="GLU-500"),
            ],
        )
        self.assertEqual(correction.state, "done")
        self.assertEqual(correction.target_quote_id, quote)
        self.assertEqual(correction.purchase_order_id, order)
        self.assertEqual(
            self.env["purchase.order"].search_count(
                [("ai_message_import_sender_id", "=", self.sender.id)]
            ),
            1,
        )
        screw = order.order_line.filtered(
            lambda ln: ln.product_id == self.product_screw
        )
        self.assertEqual(screw.product_qty, 25)
        change = correction.change_ids.filtered(lambda c: c.field_name == "product_qty")
        self.assertEqual((change.old_value, change.new_value), ("10.0", "25.0"))
        self.assertEqual(
            change.processing_ref, correction.conversation_id.processing_ref
        )
        self.assertEqual(change.reason, "The sender changes the quantity")
        self.assertEqual(change.message_ids, correction.message_ids)
        # The original values are kept.
        self.assertEqual(quote.line_ids[0].quantity, 10)
        self.assertEqual(order.state, "draft")

    def test_reapplying_a_corrected_quote_is_not_a_duplicate(self):
        quote, order = self._first_order()
        self._correction(
            quote,
            [
                self._line("Tornillo", 25, product_code="FN-100"),
                self._line("Glue", 4, product_code="GLU-500"),
            ],
        )
        quote.action_apply()
        self.assertEqual(quote.state, "done")
        self.assertEqual(quote.purchase_order_id, order)
        self.assertNotIn("duplicate", self._incident_types(quote))

    def test_reapplying_does_not_compound_the_global_discount(self):
        quote = self._run(
            self._quote(
                [self._line("Glue", 20, product_code="GLU-500", price_unit=5)],
                global_discount={"percent": 10},
            )
        )
        line = quote.purchase_order_id.order_line
        self.assertAlmostEqual(line.discount, 10.0, places=2)
        quote.action_apply()
        quote.action_apply()
        self.assertAlmostEqual(line.discount, 10.0, places=2)

    def test_correction_keeps_the_lines_it_cannot_process(self):
        quote, order = self._first_order()
        self._correction(
            quote,
            [
                self._line("Tornillo", 15, product_code="FN-100"),
                self._line("Glue", 3, product_code="GLU-500", uom="palé"),
            ],
            remove_missing_lines=True,
        )
        glue = order.order_line.filtered(lambda ln: ln.product_id == self.product_glue)
        self.assertEqual(glue.product_qty, 4, "The line pending review is kept")

    def test_correction_without_valid_lines_changes_nothing(self):
        quote, order = self._first_order()
        correction = self._correction(
            quote,
            [self._line("Tornillo", 15, product_code="FN-100", uom="palé")],
            remove_missing_lines=True,
        )
        self.assertEqual(correction.state, "pending")
        self.assertEqual(len(order.order_line), 2)
        self.assertEqual(sorted(order.order_line.mapped("product_qty")), [4, 10])

    def test_product_corrected_on_the_quote_takes_its_price(self):
        quote = self._first_order()[0]
        screw_line = quote.line_ids.filtered(lambda ln: ln.product_code == "FN-100")
        line = screw_line.purchase_line_id
        self.assertEqual(line.price_unit, 12.0)
        screw_line.product_id = self.product_box
        quote.action_apply()
        self.assertEqual(line.product_id, self.product_box)
        self.assertEqual(line.price_unit, 0.1, "Price of the new product")
        self.assertIn("Nail 30mm", line.name)

    def test_unit_changed_by_a_person_blocks_the_quantity(self):
        quote, order = self._first_order()
        screw = order.order_line.filtered(
            lambda ln: ln.product_id == self.product_screw
        )
        screw.product_uom = self.uom_dozen  # by a person
        correction = self._correction(
            quote,
            [
                self._line("Tornillo", 36, product_code="FN-100"),
                self._line("Glue", 4, product_code="GLU-500"),
            ],
        )
        self.assertEqual(screw.product_qty, 10, "36 dozens are not ordered")
        self.assertEqual(screw.product_uom, self.uom_dozen)
        self.assertIn("human_conflict", self._incident_types(correction))

    def test_order_in_another_currency_is_not_modified(self):
        quote, order = self._first_order()
        order.currency_id = self._foreign_currency()  # by a person
        correction = self._correction(
            quote, [self._line("Tornillo", 99, product_code="FN-100")]
        )
        self.assertIn("update_ambiguous", self._incident_types(correction))
        self.assertNotIn(99, order.order_line.mapped("product_qty"))

    def test_conflicts_are_not_duplicated(self):
        quote, order = self._first_order()
        screw = order.order_line.filtered(
            lambda ln: ln.product_id == self.product_screw
        )
        screw.product_qty = 12  # by a person
        correction = self._correction(
            quote,
            [
                self._line("Tornillo", 30, product_code="FN-100"),
                self._line("Glue", 4, product_code="GLU-500"),
            ],
        )
        correction.action_apply()
        correction.action_apply()
        conflicts = correction.incident_ids.filtered(
            lambda i: i.state == "open" and i.incident_type == "human_conflict"
        )
        self.assertEqual(len(conflicts), 1)

    def test_quote_of_a_confirmed_order_stays_done(self):
        quote, order = self._first_order()
        order.button_confirm()
        quote.action_apply()
        self.assertEqual(quote.state, "done")
        self.assertEqual(quote.purchase_order_id, order)
        self.assertIn("order_locked", self._incident_types(quote))

    def test_correction_adds_and_removes_lines(self):
        quote, order = self._first_order()
        self._correction(
            quote,
            [
                self._line("Tornillo", 10, product_code="FN-100"),
                self._line("Clavo", 2, product_code="NAI-30", uom="cajas"),
            ],
            remove_missing_lines=True,
        )
        self.assertEqual(
            order.order_line.product_id, self.product_screw | self.product_box
        )

    def test_human_changes_are_not_overwritten(self):
        quote, order = self._first_order()
        screw = order.order_line.filtered(
            lambda ln: ln.product_id == self.product_screw
        )
        glue = order.order_line.filtered(lambda ln: ln.product_id == self.product_glue)
        screw.product_qty = 12  # by a person
        correction = self._correction(
            quote,
            [
                self._line("Tornillo", 30, product_code="FN-100"),
                self._line("Glue", 8, product_code="GLU-500"),
            ],
        )
        self.assertEqual(screw.product_qty, 12, "The change of the person is kept")
        self.assertEqual(glue.product_qty, 8, "The other lines are updated")
        self.assertIn("human_conflict", self._incident_types(correction))
        # The field stays protected for the next correction too.
        self._correction(
            quote,
            [
                self._line("Tornillo", 40, product_code="FN-100"),
                self._line("Glue", 8, product_code="GLU-500"),
            ],
            quote_number="P-2026-001-B",
        )
        self.assertEqual(screw.product_qty, 12)

    def test_human_price_survives_a_new_quantity(self):
        quote, order = self._first_order()
        screw = order.order_line.filtered(
            lambda ln: ln.product_id == self.product_screw
        )
        screw.price_unit = 11.0  # negotiated by a person
        self._correction(
            quote,
            [
                self._line("Tornillo", 30, product_code="FN-100"),
                self._line("Glue", 4, product_code="GLU-500"),
            ],
        )
        self.assertEqual(screw.product_qty, 30)
        self.assertEqual(screw.price_unit, 11.0)

    def test_line_removed_by_a_person_is_not_added_again(self):
        quote, order = self._first_order()
        order.order_line.filtered(
            lambda ln: ln.product_id == self.product_glue
        ).unlink()
        correction = self._correction(
            quote,
            [
                self._line("Tornillo", 15, product_code="FN-100"),
                self._line("Glue", 4, product_code="GLU-500"),
            ],
        )
        self.assertEqual(order.order_line.product_id, self.product_screw)
        self.assertIn("human_conflict", self._incident_types(correction))

    def test_confirmed_order_is_never_modified(self):
        quote, order = self._first_order()
        order.button_confirm()
        correction = self._correction(
            quote, [self._line("Tornillo", 99, product_code="FN-100")]
        )
        self.assertEqual(correction.state, "pending")
        self.assertIn("order_locked", self._incident_types(correction))
        self.assertNotIn(99, order.order_line.mapped("product_qty"))

    def test_cancelled_order_is_never_modified(self):
        quote, order = self._first_order()
        order.button_cancel()
        correction = self._correction(
            quote, [self._line("Tornillo", 99, product_code="FN-100")]
        )
        self.assertIn("order_locked", self._incident_types(correction))
        self.assertEqual(order.state, "cancel")

    def test_unknown_correction_target_creates_nothing(self):
        self._first_order()
        correction = self._run(
            self._quote(
                [self._line("Tornillo", 99, product_code="FN-100")],
                relation="update",
                target_reference="AID/unknown",
                quote_number="X-1",
            )
        )
        # The unknown reference is dropped: nothing to correct unequivocally.
        self.assertEqual(correction.relation, "update")
        self.assertIn("update_ambiguous", self._incident_types(correction))
        self.assertFalse(correction.purchase_order_id)

    # ------------------------------------------------------------------
    # Duplicates
    # ------------------------------------------------------------------

    def test_same_quote_number_is_a_duplicate(self):
        quote, order = self._first_order()
        again = self._run(
            self._quote([self._line("Tornillo", 10, product_code="FN-100")])
        )
        self.assertEqual(again.state, "duplicate")
        self.assertEqual(again.duplicate_of_id, quote)
        self.assertIn("P-2026-001", again.duplicate_evidence)
        self.assertEqual(again.purchase_order_id, self.env["purchase.order"])
        self.assertEqual(
            self.env["purchase.order"].search_count(
                [("ai_message_import_sender_id", "=", self.sender.id)]
            ),
            1,
        )
        incident = again.incident_ids
        self.assertEqual(incident.incident_type, "duplicate")
        self.assertEqual(incident.purchase_order_id, order)
        # A person decides it is a different quote.
        again.action_not_duplicate()
        self.assertEqual(again.state, "done")
        self.assertNotEqual(again.purchase_order_id, order)

    def test_same_file_is_a_duplicate(self):
        def receive_pdf():
            return self._receive(
                files=[
                    {
                        "name": "p.pdf",
                        "raw": b"%PDF-1.4 same file",
                        "mimetype": "application/pdf",
                    }
                ]
            )

        first = receive_pdf()
        with self._ai(
            self._answer(
                self._quote(
                    [self._line("Tornillo", 10, product_code="FN-100")],
                    quote_number=False,
                )
            )
        ):
            self._process()
        second = receive_pdf()
        with self._ai(
            self._answer(
                self._quote(
                    [self._line("Tornillo", 10, product_code="FN-100")],
                    quote_number=False,
                )
            )
        ):
            self._process()
        self.assertEqual(second.conversation_id.document_ids.state, "duplicate")
        self.assertEqual(
            second.conversation_id.document_ids.duplicate_of_id,
            first.conversation_id.document_ids,
        )

    def test_duplicate_applied_as_correction(self):
        order = self._first_order()[1]
        again = self._run(
            self._quote([self._line("Tornillo", 70, product_code="FN-100")])
        )
        self.assertEqual(again.state, "duplicate")
        again.action_apply_as_correction()
        self.assertEqual(again.purchase_order_id, order)
        self.assertIn(70, order.order_line.mapped("product_qty"))

    def test_duplicate_detected_by_ai(self):
        quote, _order = self._first_order()
        again = self._run(
            self._quote(
                [self._line("Tornillo", 10, product_code="FN-100")],
                relation="duplicate",
                target_reference=quote.name,
                relation_reason="Same PDF sent again",
            )
        )
        self.assertEqual(again.state, "duplicate")
        self.assertEqual(again.duplicate_of_id, quote)

    # ------------------------------------------------------------------
    # Learned equivalences
    # ------------------------------------------------------------------

    def test_correction_is_learned_for_the_client_and_vendor(self):
        self.config.auto_create_product = False
        quote = self._run(
            self._quote([self._line("Cola blanca", 2, product_code="CB-1")])
        )
        self.assertIn("product", self._incident_types(quote))
        quote.line_ids.product_id = self.product_glue
        quote.action_apply()
        self.assertEqual(
            quote.purchase_order_id.order_line.product_id, self.product_glue
        )
        mapping = self.env["ai.message.import.product.mapping"].search(
            [("sender_id", "=", self.sender.id)]
        )
        self.assertEqual(mapping.product_id, self.product_glue)
        self.assertEqual(mapping.partner_id, self.vendor)
        # Next quote of the same sender and vendor: found by the mapping.
        next_quote = self._run(
            self._quote(
                [self._line("Cola blanca", 5, product_code="CB-1")], quote_number="P-9"
            )
        )
        self.assertEqual(next_quote.line_ids.product_match, "mapping")
        self.assertEqual(
            next_quote.purchase_order_id.order_line.product_id, self.product_glue
        )

    def test_learned_equivalence_is_not_shared_between_clients(self):
        self.config.auto_create_product = False
        quote = self._run(
            self._quote([self._line("Cola blanca", 2, product_code="CB-1")])
        )
        quote.line_ids.product_id = self.product_glue
        other = self.env["mail.message.import.sender"].create({"name": "Other sender"})
        self.env["mail.message.import.address"].create(
            {
                "sender_id": other.id,
                "channel_type": self.channel.channel_type,
                "address": "+34600999888",
            }
        )
        message = self._receive("Presupuesto", sender="+34600999888")
        with self._ai(
            self._answer(
                self._quote([self._line("Cola blanca", 2, product_code="CB-1")])
            )
        ):
            self._process()
        other_quote = message.conversation_id.document_ids
        self.assertEqual(other_quote.sender_id, other)
        self.assertFalse(other_quote.line_ids.product_id)
        self.assertIn("product", self._incident_types(other_quote))

    def test_product_corrected_on_the_order_is_learned(self):
        self.config.auto_create_product = True
        quote = self._run(
            self._quote(
                [self._line("Cola especial", 2, product_code="CE-9", price_unit=3)]
            )
        )
        line = quote.purchase_order_id.order_line
        line.product_id = self.product_glue  # the buyer knows better
        mapping = self.env["ai.message.import.product.mapping"].search(
            [("sender_id", "=", self.sender.id), ("key", "=", "ce9")]
        )
        self.assertEqual(mapping.product_id, self.product_glue)
        self.assertEqual(mapping.source, "manual")
        self.assertEqual(quote.line_ids.product_id, self.product_glue)

    # ------------------------------------------------------------------
    # Confirmation
    # ------------------------------------------------------------------

    def test_automation_never_confirms_nor_cancels(self):
        order = self._first_order()[1]
        automated = order.with_context(**{AUTOMATION_CONTEXT_KEY: True})
        with self.assertRaises(UserError):
            automated.button_confirm()
        with self.assertRaises(UserError):
            automated.button_cancel()
        with self.assertRaises(UserError):
            automated.write({"state": "purchase"})
        self.assertEqual(order.state, "draft")

    def test_confirmation_warns_about_open_incidents(self):
        quote = self._run(
            self._quote([self._line("Brush", 2, product_code="BRU-01")])  # zero cost
        )
        order = quote.purchase_order_id
        self.assertTrue(order.ai_message_import_open_incident_count)
        action = order.action_ai_message_confirm()
        self.assertEqual(action["res_model"], "ai.message.import.order.confirm")
        wizard = Form(
            self.env["ai.message.import.order.confirm"].with_context(
                **action["context"]
            )
        ).save()
        self.assertIn("Zero cost", wizard.incident_summary)
        wizard.action_confirm()
        self.assertEqual(order.state, "purchase")

    def test_confirmation_without_incidents(self):
        _quote, order = self._first_order()
        order.ai_message_import_incident_ids.action_dismiss()
        order.action_ai_message_confirm()
        self.assertEqual(order.state, "purchase")
