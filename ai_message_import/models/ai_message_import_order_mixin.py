# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models
from odoo.exceptions import UserError

from ..services.tools import AUTOMATION_CONTEXT_KEY

MANAGER_GROUP = "mail_message_import.group_mail_message_import_manager"


class AiMessageImportOrderMixin(models.AbstractModel):
    """Orders created from the documents received.

    Each document type (purchase, sale...) adds it to its orders, with the
    One2many fields of its quotes, incidents and changes, and blocks their
    confirmation and cancellation in the technical context of the module.
    """

    _name = "ai.message.import.order.mixin"
    _description = "Order Created from a Received Document"

    #: Field of the quotes, incidents and changes linked to the order.
    _ai_message_import_link = None

    ai_message_import_sender_id = fields.Many2one(
        "mail.message.import.sender",
        string="Document sender",
        readonly=True,
        copy=False,
        index="btree_not_null",
        groups=MANAGER_GROUP,
    )
    ai_message_import_open_incident_count = fields.Integer(
        string="Open document incidents",
        compute="_compute_ai_message_open_incident_count",
    )
    ai_message_import_open_incident_summary = fields.Text(
        string="Open document incidents summary",
        compute="_compute_ai_message_open_incident_count",
    )
    ai_message_import_ai_values = fields.Json(
        string="Values set by the module", copy=False, groups="base.group_no_one"
    )
    ai_message_import_channel = fields.Char(
        string="Received by", compute="_compute_ai_message_origin"
    )
    ai_message_import_address = fields.Char(
        string="Received from", compute="_compute_ai_message_origin"
    )
    ai_message_import_origin = fields.Char(
        string="Origin of the document",
        compute="_compute_ai_message_origin",
        help="The channel and the phone or email address the documents of the "
        "order came from.",
    )

    def _compute_ai_message_origin(self):
        # Shown to every user of the orders, as the incidents.
        quotes = (
            self.env["ai.message.import.document"]
            .sudo()
            .search([(self._ai_message_import_link, "in", self.ids)], order="id desc")
        )
        channels = dict(
            self.env["mail.message.import.channel"]
            ._fields["channel_type"]
            ._description_selection(self.env)
        )
        for order in self:
            own = quotes.filtered(
                lambda q, order=order: q[self._ai_message_import_link] == order
            )
            last = own[:1]
            order.ai_message_import_channel = (
                channels.get(last.channel_id.channel_type) or False
            )
            order.ai_message_import_address = (
                last.authorized_address_id.address or last.sender_address or False
            )
            order.ai_message_import_origin = (
                ", ".join(dict.fromkeys(own.mapped("origin_display"))) or False
            )

    def _compute_ai_message_open_incident_count(self):
        # Every user of the orders is warned, even without access to the
        # application.
        incidents = (
            self.env["mail.message.import.incident"]
            .sudo()
            .search(
                [(self._ai_message_import_link, "in", self.ids), ("state", "=", "open")]
            )
        )
        for order in self:
            own = incidents.filtered(
                lambda i, order=order: i[self._ai_message_import_link] == order
            )
            order.ai_message_import_open_incident_count = len(own)
            order.ai_message_import_open_incident_summary = "\n".join(
                f"- {incident.name}" for incident in own
            )

    def _ai_message_forbid_automation(self):
        if self.env.context.get(AUTOMATION_CONTEXT_KEY):
            raise UserError(
                self.env._(
                    "Orders are never confirmed nor cancelled automatically: a "
                    "person must do it."
                )
            )

    def write(self, vals):
        if "state" in vals:
            self._ai_message_forbid_automation()
        return super().write(vals)

    def _ai_message_confirm(self):
        """Confirm the order, as its button does."""
        raise NotImplementedError()

    def _ai_message_learn_ai_products(self):
        """A person confirmed the order: the products the AI chose and nobody
        changed are right, learn them."""
        Mapping = self.env["ai.message.import.product.mapping"].sudo()
        for line in self.sudo().order_line.filtered(
            "ai_message_import_document_line_id"
        ):
            qline = line.ai_message_import_document_line_id
            if qline.product_match == "ai" and qline.product_id == line.product_id:
                Mapping._learn(qline, line.product_id, source="ai")

    def action_ai_message_confirm(self):
        """Confirm, after a warning when document incidents are still open."""
        self.ensure_one()
        if not self.ai_message_import_open_incident_count:
            return self._ai_message_confirm()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Open incidents"),
            "res_model": "ai.message.import.order.confirm",
            "view_mode": "form",
            "target": "new",
            "context": {"default_res_model": self._name, "default_res_id": self.id},
        }

    def _ai_message_action(self, xmlid, context=None):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(xmlid)
        action["domain"] = [(self._ai_message_import_link, "=", self.id)]
        action["context"] = context or {}
        return action

    def action_ai_message_view_incidents(self):
        return self._ai_message_action(
            "mail_message_import.action_mail_message_import_incident",
            {"search_default_open": 1},
        )

    def action_ai_message_view_quotes(self):
        return self._ai_message_action(
            "ai_message_import.action_ai_message_import_document"
        )


class AiMessageImportOrderLineMixin(models.AbstractModel):
    """Lines of the orders created from the documents received."""

    _name = "ai.message.import.order.line.mixin"
    _description = "Order Line Created from a Received Document"

    ai_message_import_document_line_id = fields.Many2one(
        "ai.message.import.document.line",
        string="Quoted line",
        readonly=True,
        copy=False,
        index="btree_not_null",
        groups=MANAGER_GROUP,
    )
    ai_message_import_line_kind = fields.Selection(
        [("product", "Quoted product"), ("freight", "Quoted transport")],
        string="Origin of the line",
        readonly=True,
        copy=False,
    )
    ai_message_import_ai_values = fields.Json(
        string="Values set by the module", copy=False, groups="base.group_no_one"
    )

    def write(self, vals):
        res = super().write(vals)
        if vals.get("product_id") and not self.env.context.get(AUTOMATION_CONTEXT_KEY):
            self._ai_message_learn_product()
        return res

    def _ai_message_learn_product(self):
        """A person replaced the product of a quoted line: learn it."""
        for line in self.sudo().filtered("ai_message_import_document_line_id"):
            qline = line.ai_message_import_document_line_id.with_context(
                **{AUTOMATION_CONTEXT_KEY: True}
            )
            qline.write({"product_id": line.product_id.id, "product_match": "manual"})
            self.env["ai.message.import.product.mapping"].sudo()._learn(
                qline, line.product_id, source="manual"
            )

    def unlink(self):
        quote_lines = self.sudo().ai_message_import_document_line_id
        if not self.env.context.get(AUTOMATION_CONTEXT_KEY):
            # Removed by a person: later corrections must not add it again.
            quote_lines = quote_lines.with_context(**{AUTOMATION_CONTEXT_KEY: True})
            quote_lines.write({"state": "removed"})
        return super().unlink()
