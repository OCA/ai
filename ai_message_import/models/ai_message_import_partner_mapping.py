# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..services.tools import normalize_company_name


class AiMessageImportPartnerMapping(models.Model):
    """Equivalence between the name a partner is written with and its contact.

    Short orders name the customer or the vendor by an alias ("fruveicod"). When
    a person selects the partner of such a document, the name is learned (or a
    person adds it by hand): the next documents of the same sender that write it
    find the partner.
    """

    _name = "ai.message.import.partner.mapping"
    _description = "Learned Partner Equivalence"
    _order = "sender_id, key"
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
    key = fields.Char(
        compute="_compute_key", store=True, index=True, help="Normalized name."
    )
    partner_text = fields.Char(
        string="As written",
        required=True,
        help="The name as the documents write it, e.g. an alias.",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Vendor / Customer",
        required=True,
        ondelete="cascade",
        check_company=True,
    )
    usage_count = fields.Integer(default=0, readonly=True)
    last_used = fields.Datetime(readonly=True)

    _sql_constraints = [
        (
            "key_uniq",
            "unique(sender_id, key)",
            "This name is already learned for the sender.",
        ),
    ]

    @api.depends("partner_text")
    def _compute_key(self):
        for mapping in self:
            mapping.key = normalize_company_name(mapping.partner_text) or False

    @api.constrains("key")
    def _check_key(self):
        for mapping in self.filtered(lambda m: not m.key):
            raise ValidationError(
                self.env._(
                    "Write the name as the documents write it: %(text)s cannot "
                    "be recognised.",
                    text=mapping.partner_text or "-",
                )
            )

    @api.model
    def _learn(self, quote, partner):
        """Remember that the partner written in ``document`` is ``partner``."""
        key = normalize_company_name(quote.partner_name)
        if not key or not partner:
            return self.browse()
        values = {
            "partner_id": partner.id,
            "partner_text": quote.partner_name,
            "last_used": fields.Datetime.now(),
        }
        mapping = self.sudo().search(
            [("sender_id", "=", quote.sender_id.id), ("key", "=", key)], limit=1
        )
        if mapping:
            mapping.write(dict(values, usage_count=mapping.usage_count + 1))
            return mapping
        return self.sudo().create(
            dict(values, sender_id=quote.sender_id.id, usage_count=1)
        )
