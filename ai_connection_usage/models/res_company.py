# Copyright 2026 Nimarosa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    ai_usage_month_cap = fields.Monetary(
        string="AI Monthly Spending Cap",
        currency_field="currency_id",
        groups="base.group_system",
        help="Maximum spend on AI calls per calendar month for this company, in "
        "the company currency. Calls are refused once it is reached. Leave it "
        "at zero for no cap.",
    )
