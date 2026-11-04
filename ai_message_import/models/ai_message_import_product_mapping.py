# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..services.tools import normalize_code, normalize_text


class AiMessageImportProductMapping(models.Model):
    """Equivalence between a product written by a partner and an Odoo product.

    It is learned from the corrections of the users, or added by hand, and only
    applies to the documents of the same sender and the same partner (vendor or
    customer).
    """

    _name = "ai.message.import.product.mapping"
    _description = "Learned Product Equivalence"
    _order = "sender_id, partner_id, key"
    _check_company_auto = True

    sender_id = fields.Many2one(
        "mail.message.import.sender",
        string="Sender",
        required=True,
        ondelete="cascade",
        index=True,
        default=lambda self: self.env[
            "mail.message.import.sender"
        ]._single_of_company(),
    )
    company_id = fields.Many2one(related="sender_id.company_id", store=True)
    partner_id = fields.Many2one(
        "res.partner",
        string="Vendor / Customer",
        required=True,
        ondelete="cascade",
        index=True,
    )
    key_type = fields.Selection(
        [("code", "Reference"), ("description", "Description")],
        string="Reference or description",
        required=True,
        default="code",
        help="Whether the documents name the product by its reference or by its "
        "description.",
    )
    key = fields.Char(
        compute="_compute_key",
        store=True,
        index=True,
        help="Normalized reference or text.",
    )
    partner_text = fields.Char(
        string="As written",
        required=True,
        help="The reference or the description as the documents write it.",
    )
    product_id = fields.Many2one(
        "product.product", required=True, ondelete="cascade", check_company=True
    )
    source = fields.Selection(
        [
            ("user", "Added by a user"),
            ("manual", "Correction of a user"),
            ("created", "Product created"),
            ("ai", "Choice of the AI, confirmed"),
        ],
        default="user",
        required=True,
        readonly=True,
    )
    usage_count = fields.Integer(default=0, readonly=True)
    last_used = fields.Datetime(readonly=True)

    _sql_constraints = [
        (
            "key_uniq",
            "unique(sender_id, partner_id, key_type, key)",
            "This equivalence already exists for the sender and the partner.",
        ),
    ]

    @api.depends("key_type", "partner_text")
    def _compute_key(self):
        for mapping in self:
            normalize = normalize_code if mapping.key_type == "code" else normalize_text
            mapping.key = normalize(mapping.partner_text) or False

    @api.constrains("key")
    def _check_key(self):
        for mapping in self.filtered(lambda m: not m.key):
            raise ValidationError(
                _(
                    "Write the reference or the description as the documents "
                    "write it: %(text)s cannot be recognised.",
                    text=mapping.partner_text or "-",
                )
            )

    @api.model
    def _learn(self, qline, product, source="manual"):
        """Remember that the product of ``qline`` is ``product``."""
        partner = qline.document_id.partner_id.commercial_partner_id
        if not partner or not product:
            return self.browse()
        code = normalize_code(qline.product_code)
        key_type, key, text = (
            ("code", code, qline.product_code)
            if code
            else ("description", normalize_text(qline.description), qline.description)
        )
        if not key:
            return self.browse()
        mapping = self.sudo().search(
            [
                ("sender_id", "=", qline.document_id.sender_id.id),
                ("partner_id", "=", partner.id),
                ("key_type", "=", key_type),
                ("key", "=", key),
            ],
            limit=1,
        )
        values = {
            "product_id": product.id,
            "source": source,
            "partner_text": text,
            "last_used": fields.Datetime.now(),
        }
        if mapping:
            mapping.write(dict(values, usage_count=mapping.usage_count + 1))
            return mapping
        return self.sudo().create(
            dict(
                values,
                sender_id=qline.document_id.sender_id.id,
                partner_id=partner.id,
                key_type=key_type,
                usage_count=1,
            )
        )
