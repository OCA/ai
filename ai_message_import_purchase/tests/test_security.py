# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError, UserError
from odoo.tests import new_test_user, tagged

from .common import AiMessagePurchaseCase

MANAGER = "mail_message_import.group_mail_message_import_manager"


@tagged("post_install", "-at_install")
class TestSecurity(AiMessagePurchaseCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_b = cls.env["res.company"].create({"name": "Company B"})
        cls.sender_b = cls.env["mail.message.import.sender"].create(
            {"name": "Client B", "company_id": cls.company_b.id}
        )
        cls.manager_a = new_test_user(
            cls.env,
            login="ai_message_manager_a",
            groups=f"{MANAGER},purchase.group_purchase_user",
            company_id=cls.company.id,
            company_ids=[cls.company.id],
        )
        cls.manager_ab = new_test_user(
            cls.env,
            login="ai_message_manager_ab",
            groups=MANAGER,
            company_id=cls.company.id,
            company_ids=[cls.company.id, cls.company_b.id],
        )
        cls.buyer = new_test_user(
            cls.env,
            login="ai_message_buyer",
            groups="purchase.group_purchase_user",
            company_id=cls.company.id,
        )

    def test_application_requires_the_group(self):
        with self.assertRaises(AccessError):
            self.env["mail.message.import.sender"].with_user(self.buyer).search([])
        with self.assertRaises(AccessError):
            self.env["mail.message.import.message"].with_user(self.buyer).search([])
        menu = self.env.ref("mail_message_import.menu_mail_message_import_root")
        visible = self.env["ir.ui.menu"].with_user(self.buyer)._visible_menu_ids()
        self.assertNotIn(menu.id, visible)

    def test_group_is_not_an_administrator(self):
        group = self.env.ref(MANAGER)
        self.assertNotIn(self.env.ref("base.group_system"), group.implied_ids)
        self.assertNotIn(
            self.env.ref("purchase.group_purchase_manager"), group.implied_ids
        )
        with self.assertRaises(AccessError):
            self.env["res.config.settings"].with_user(self.manager_ab).create(
                {}
            ).execute()

    def test_company_isolation(self):
        Client = self.env["mail.message.import.sender"]
        mine = [("id", "in", (self.sender | self.sender_b).ids)]
        self.assertEqual(Client.with_user(self.manager_a).search(mine), self.sender)
        self.assertEqual(
            Client.with_user(self.manager_ab)
            .with_context(allowed_company_ids=[self.company.id, self.company_b.id])
            .search(mine),
            self.sender | self.sender_b,
        )

    def test_files_follow_the_rules_of_their_message(self):
        message = self._receive(
            files=[
                {
                    "name": "p.pdf",
                    "raw": b"%PDF-1.4 secret",
                    "mimetype": "application/pdf",
                }
            ]
        )
        attachment = message.attachment_ids
        attachment.with_user(self.manager_a).check("read")
        with self.assertRaises(AccessError):
            attachment.with_user(self.buyer).check("read")

    def test_quote_is_applied_with_purchase_rights_only(self):
        self.config.auto_create_product = False
        quote = self._run(self._quote([self._line("Cola", 2, product_code="CB-1")]))
        quote.line_ids.product_id = self.product_glue
        manager_without_purchase = new_test_user(
            self.env, login="ai_message_no_purchase", groups=MANAGER
        )
        with self.assertRaises(UserError):
            quote.with_user(manager_without_purchase).action_apply()
        quote.with_user(self.manager_a).action_apply()
        self.assertEqual(quote.state, "done")

    def test_orders_are_created_in_the_company_of_the_client(self):
        partner_b = self.env["res.partner"].create(
            {"name": "Vendor B", "vat": "ESB55555551", "company_id": self.company_b.id}
        )
        self.env["mail.message.import.address"].create(
            {
                "sender_id": self.sender_b.id,
                "channel_type": self.channel.channel_type,
                "address": "+34611000222",
            }
        )
        # The channel belongs to the company B.
        self.channel.company_id = self.company_b
        message = self._receive("Presupuesto", sender="+34611000222")
        self.assertEqual(message.company_id, self.company_b)
        with self._ai(
            self._answer(
                self._quote(
                    [self._line("Cinta", 2, product_code="CA-50", price_unit=4)],
                    partner={"name": "Vendor B", "vat": "B55555551", "confidence": 0.9},
                    currency=self.company_b.currency_id.name,
                )
            )
        ):
            self._process()
        order = message.conversation_id.document_ids.purchase_order_id
        self.assertEqual(order.company_id, self.company_b)
        self.assertEqual(order.partner_id, partner_b)
        self.assertEqual(order.order_line.product_id.company_id, self.company_b)
        self.assertNotIn(self.vendor, order.partner_id)

    def test_ai_connections_are_for_administrators_only(self):
        # The managers choose the connection of their company, the
        # administrators create the connections and keep their keys.
        Connection = self.env["ai.connection"].with_user(self.manager_a)
        self.assertTrue(Connection.has_access("read"))
        self.assertFalse(Connection.has_access("create"))
        config = self.config.with_user(self.manager_a)
        config.ai_connection_id = False
        self.assertFalse(config.ai_configured)

    def test_buyers_without_the_application_keep_their_form(self):
        quote = self._run(self._quote([self._line("Brush", 2, product_code="BRU-01")]))
        order = quote.purchase_order_id.with_user(self.buyer)
        views = order.get_views([(False, "form")])
        self.assertNotIn(
            "ai_message_import_sender_id", views["models"]["purchase.order"]["fields"]
        )
        self.assertTrue(
            order.ai_message_import_open_incident_count, "Buyers are warned too"
        )
        order.action_ai_message_confirm()
