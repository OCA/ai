# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MailMessageImportConfig(models.Model):
    _inherit = "mail.message.import.config"

    auto_create_customer = fields.Boolean(
        string="Create customers",
        default=True,
        help="Create the customer of an order when it does not exist, only with "
        "reliable data: its name and a VAT number, email, phone or address, "
        "identified with enough confidence.",
    )
    customer_min_confidence = fields.Float(
        string="Minimum customer confidence", default=0.8, digits=(3, 2)
    )

    @api.constrains("customer_min_confidence")
    def _check_customer_min_confidence(self):
        for config in self:
            if not 0 <= config.customer_min_confidence <= 1:
                raise ValidationError(self.env._("The confidences go from 0 to 1."))
