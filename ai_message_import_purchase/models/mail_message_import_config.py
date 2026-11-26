# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MailMessageImportConfig(models.Model):
    _inherit = "mail.message.import.config"

    auto_create_vendor = fields.Boolean(
        string="Create vendors",
        default=True,
        help="Create the vendor of a document when it does not exist and it was "
        "identified with enough confidence.",
    )
    vendor_min_confidence = fields.Float(
        string="Minimum vendor confidence", default=0.8, digits=(3, 2)
    )
    auto_create_product = fields.Boolean(
        string="Create products",
        default=True,
        help="Create the products of a vendor quote that do not exist when its "
        "data is complete and reliable.",
    )
    product_min_confidence = fields.Float(
        string="Minimum product confidence", default=0.8, digits=(3, 2)
    )

    @api.constrains("vendor_min_confidence", "product_min_confidence")
    def _check_purchase_confidences(self):
        for config in self:
            for confidence in (
                config.vendor_min_confidence,
                config.product_min_confidence,
            ):
                if not 0 <= confidence <= 1:
                    raise ValidationError(self.env._("The confidences go from 0 to 1."))
