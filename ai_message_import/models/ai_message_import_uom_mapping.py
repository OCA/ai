# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..services.tools import normalize_text


class AiMessageImportUomMapping(models.Model):
    """Equivalence between a unit written by a sender and a unit of Odoo.

    Orders write units Odoo does not know ("caja de kilo", "manojo"). When a
    person sets the unit of such a line, the text is learned (or a person adds
    it by hand): the next documents of the same sender that write it use the
    unit, for the products whose unit is of the same category.
    """

    _name = "ai.message.import.uom.mapping"
    _description = "Learned Unit Equivalence"
    _order = "sender_id, key"

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
        compute="_compute_key", store=True, index=True, help="Normalized unit."
    )
    uom_text = fields.Char(
        string="As written",
        required=True,
        help="The unit as the documents write it, e.g. 'saco' or 'caja de kilo'.",
    )
    uom_id = fields.Many2one(
        "uom.uom", string="Unit of measure", required=True, ondelete="cascade"
    )
    usage_count = fields.Integer(default=0, readonly=True)
    last_used = fields.Datetime(readonly=True)

    _sql_constraints = [
        (
            "key_uniq",
            "unique(sender_id, key)",
            "This unit is already learned for the sender.",
        ),
    ]

    @api.depends("uom_text")
    def _compute_key(self):
        for mapping in self:
            mapping.key = normalize_text(mapping.uom_text) or False

    @api.constrains("key")
    def _check_key(self):
        for mapping in self.filtered(lambda m: not m.key):
            raise ValidationError(
                _(
                    "Write the unit as the documents write it: %(text)s cannot "
                    "be recognised.",
                    text=mapping.uom_text or "-",
                )
            )

    @api.model
    def _learn(self, qline, uom):
        """Remember that the unit written in ``qline`` is ``uom``."""
        key = normalize_text(qline.uom_text)
        if not key or not uom:
            return self.browse()
        sender = qline.document_id.sender_id
        values = {
            "uom_id": uom.id,
            "uom_text": qline.uom_text,
            "last_used": fields.Datetime.now(),
        }
        mapping = self.sudo().search(
            [("sender_id", "=", sender.id), ("key", "=", key)], limit=1
        )
        if mapping:
            mapping.write(dict(values, usage_count=mapping.usage_count + 1))
            return mapping
        return self.sudo().create(dict(values, sender_id=sender.id, usage_count=1))
