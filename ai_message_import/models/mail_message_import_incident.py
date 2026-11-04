# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services.tools import (
    AUTOMATION_CONTEXT_KEY,
    NO_AUTO_APPLY_KEY,
    normalize_code,
    normalize_company_name,
    normalize_text,
)

INCIDENT_TYPES = [
    ("ai_error", "AI error"),
    ("invalid_ai_response", "Invalid AI answer"),
    ("unsupported_file", "File not analysed"),
    ("no_document", "No document"),
    ("partner", "Vendor / Customer"),
    ("product", "Product"),
    ("uom", "Unit of measure"),
    ("invalid_line", "Incomplete line"),
    ("price_zero", "Zero price"),
    ("tax_missing", "Missing tax"),
    ("tax_difference", "Tax difference"),
    ("currency", "Currency"),
    ("discount", "Discount"),
    ("freight", "Transport charges"),
    ("delivery_date", "Delivery date"),
    ("payment_term", "Payment terms"),
    ("delivery_address", "Delivery address"),
    ("pack_size", "Units per box"),
    ("total_difference", "Totals difference"),
    ("duplicate", "Possible duplicate"),
    ("update_ambiguous", "Ambiguous correction"),
    ("order_locked", "Order not modifiable"),
    ("human_conflict", "Manual change conflict"),
]

# Missing data; the failures of the AI are technical, the rest is assessed.
INCOMPLETE_TYPES = {
    "unsupported_file",
    "no_document",
    "partner",
    "product",
    "uom",
    "invalid_line",
    "currency",
    "freight",
}

# Failures of a whole conversation with the AI, solved by processing it again.
AI_RETRY_TYPES = ("ai_error", "invalid_ai_response")

# Incidents that keep the document, or one of its lines, out of its order: once
# a person solves them, the document is applied again by itself.
BLOCKING_TYPES = (
    "partner",
    "product",
    "uom",
    "invalid_line",
    "no_document",
    "currency",
    "processing_error",
)

# Incidents solved by choosing, on the incident, the record to use.
FIX_FIELDS = {
    "partner": "fix_partner_id",
    "product": "fix_product_id",
    "uom": "fix_uom_id",
}


class MailMessageImportIncident(models.Model):
    """What the AI or the documents left for a person to review."""

    _inherit = "mail.message.import.incident"

    incident_type = fields.Selection(
        selection_add=INCIDENT_TYPES,
        ondelete={key: "cascade" for key, _label in INCIDENT_TYPES},
    )
    original_values = fields.Text(
        help="Values of the document or of the file concerned."
    )
    document_id = fields.Many2one(
        "ai.message.import.document", readonly=True, index=True
    )
    document_line_id = fields.Many2one(
        "ai.message.import.document.line", string="Document line", readonly=True
    )
    # The record a person chooses to solve the incident
    fix_partner_id = fields.Many2one(
        "res.partner",
        string="Contact to use",
        domain="[('company_id', 'in', [company_id, False])]",
        help="Contact of the document. The name it was written with is learned "
        "for the sender.",
    )
    fix_product_id = fields.Many2one(
        "product.product",
        string="Product to use",
        domain="[('company_id', 'in', [company_id, False])]",
        help="Product of the line. The equivalence is learned for the sender and "
        "the vendor or customer.",
    )
    fix_uom_id = fields.Many2one(
        "uom.uom",
        string="Unit to use",
        domain="[('category_id', '=', line_uom_category_id)]",
        help="Unit of the quantity of the line. The unit as written is learned "
        "for the sender.",
    )
    line_product_id = fields.Many2one(
        related="document_line_id.product_id", string="Product of the line"
    )
    line_uom_category_id = fields.Many2one(
        related="document_line_id.product_id.uom_id.category_id",
        string="Unit category of the line",
    )
    can_fix = fields.Boolean(compute="_compute_can_fix")

    @api.model
    def _category_of(self, incident_type):
        if incident_type in INCOMPLETE_TYPES:
            return "incomplete"
        return super()._category_of(incident_type)

    @api.model
    def _retry_types(self):
        return super()._retry_types() + AI_RETRY_TYPES

    @api.depends("document_id.state")
    def _compute_can_retry(self):
        """An incident of a document applies it again."""
        with_document = self.filtered("document_id")
        for incident in with_document:
            incident.can_retry = (
                incident.state == "open" and incident.document_id.state != "cancelled"
            )
        return super(
            MailMessageImportIncident, self - with_document
        )._compute_can_retry()

    @api.depends(
        "incident_type", "state", "document_id.state", "document_line_id.product_id"
    )
    def _compute_can_fix(self):
        for incident in self:
            # Partners are set on the document, products and units on its line.
            needs = {
                "partner": incident.document_id,
                "product": incident.document_line_id,
                "uom": incident.line_product_id,
            }
            incident.can_fix = (
                incident.state == "open"
                and bool(needs.get(incident.incident_type))
                and incident.document_id.state != "cancelled"
            )

    def action_resolve(self):
        incidents = self.filtered(lambda i: i.state == "open")
        res = super().action_resolve()
        # What kept the order from being created is solved: create it.
        incidents.filtered(
            lambda i: i.incident_type in BLOCKING_TYPES
        ).document_id._apply_after_fix()
        return res

    def action_retry(self):
        """The incident of a document applies it again; the others retry their
        conversation."""
        with_document = self.filtered("document_id")
        for incident in with_document:
            if not incident.can_retry:
                raise UserError(
                    self.env._(
                        "The incident %(name)s cannot be retried.", name=incident.name
                    )
                )
            incident.document_id.action_apply()
        return super(MailMessageImportIncident, self - with_document).action_retry()

    def action_apply_fix(self):
        """Use the record chosen on the incident and learn it; the open incidents
        of other lines or documents written the same way are solved with it too.
        Their documents are applied again."""
        documents = self.env["ai.message.import.document"]
        for incident in self:
            if incident.state != "open":
                # Already solved as the same incident of another one.
                continue
            if not incident.can_fix:
                raise UserError(
                    self.env._(
                        "The incident %(name)s cannot be solved by choosing a record.",
                        name=incident.name,
                    )
                )
            choice = incident[FIX_FIELDS[incident.incident_type]]
            if not choice:
                raise UserError(
                    self.env._(
                        "Choose what to use for the incident %(name)s.",
                        name=incident.name,
                    )
                )
            same = incident._same_open_incidents(choice)
            incident._use_choice(choice)
            same._use_choice(choice, learned=True)
            incident._close(
                "resolved",
                self.env._(
                    "%(choice)s chosen on the incident, learned for the next "
                    "documents. Open incidents solved with it too: %(count)s.",
                    choice=choice.display_name,
                    count=len(same),
                ),
            )
            same._close(
                "resolved",
                self.env._(
                    "Solved with %(choice)s, chosen on the same incident of "
                    "%(document)s.",
                    choice=choice.display_name,
                    document=incident.document_id.name,
                ),
            )
            documents |= (incident | same).document_id
        documents._check_order_rights()
        for document in documents:
            document._apply_quote(document._manual_ref())
        return True

    def _written_key(self):
        """How the document wrote the value of the incident: the incidents with
        the same key are solved with the same record."""
        self.ensure_one()
        if self.incident_type == "partner":
            return normalize_company_name(self.document_id.partner_name)
        qline = self.document_line_id
        if self.incident_type == "uom":
            return normalize_text(qline.uom_text)
        if self.incident_type == "product":
            # Learned for a partner, by reference or else by description.
            partner = self.document_id.partner_id.commercial_partner_id
            code = normalize_code(qline.product_code)
            text = code or normalize_text(qline.description)
            if not partner or not text:
                return False
            return (partner.id, bool(code), text)
        return False

    def _same_open_incidents(self, choice):
        """The other open incidents written as this one, that ``choice`` solves."""
        self.ensure_one()
        key = self._written_key()
        if not key:
            return self.browse()
        candidates = self.search(
            [
                ("id", "!=", self.id),
                ("state", "=", "open"),
                ("incident_type", "=", self.incident_type),
                ("sender_id", "=", self.sender_id.id),
                ("document_id.state", "!=", "cancelled"),
                ("document_id.document_type", "=", self.document_id.document_type),
            ]
        )
        return candidates.filtered(
            lambda i: i.can_fix
            and i._written_key() == key
            and (
                i.incident_type != "uom" or i.line_uom_category_id == choice.category_id
            )
        )

    def _use_choice(self, choice, learned=False):
        """Set ``choice`` on the documents of the incidents. Chosen by a person,
        it is learned; ``learned`` when it comes from another incident. The
        documents are applied again afterwards, all together."""
        context = (
            {AUTOMATION_CONTEXT_KEY: True} if learned else {NO_AUTO_APPLY_KEY: True}
        )
        for incident in self:
            incident[FIX_FIELDS[incident.incident_type]] = choice
            if incident.incident_type == "partner":
                values = {"partner_id": choice.id}
                if learned:
                    values["partner_match_method"] = "mapping"
                incident.document_id.with_context(**context).write(values)
            elif incident.incident_type == "product":
                values = {"product_id": choice.id}
                if learned:
                    values["product_match"] = "mapping"
                incident.document_line_id.with_context(**context).write(values)
            else:
                incident.document_line_id.with_context(**context).write(
                    {"uom_id": choice.id}
                )

    def _get_order(self):
        """The order of the incident, given by the module of its type."""
        self.ensure_one()
        return False

    def action_open_order(self):
        self.ensure_one()
        order = self._get_order()
        if not order:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": order._name,
            "res_id": order.id,
            "view_mode": "form",
        }

    def action_open_document(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "ai.message.import.document",
            "res_id": self.document_id.id,
            "view_mode": "form",
        }
