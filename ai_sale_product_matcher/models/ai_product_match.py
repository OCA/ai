# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo import api, fields, models


class AiProductMatch(models.Model):
    _name = "ai.product.match"
    _description = "AI Product Match"
    _order = "weighted_percent desc, match_percent desc"

    order_id = fields.Many2one(
        "sale.order", required=True, ondelete="cascade", index=True
    )
    product_tmpl_id = fields.Many2one(
        "product.template", string="Product Template", required=True
    )
    product_id = fields.Many2one("product.product", string="Product Variant")
    match_count = fields.Integer(string="Matched", readonly=True)
    total_required = fields.Integer(string="Required Keys", readonly=True)
    match_percent = fields.Float(string="Match %", readonly=True, digits=(5, 1))
    weighted_percent = fields.Float(string="Weighted %", readonly=True, digits=(5, 1))
    matched_keys = fields.Text(string="Matched Keys (JSON)", readonly=True)
    mismatched_keys = fields.Text(string="Mismatched Keys (JSON)", readonly=True)
    missing_keys = fields.Text(string="Missing Keys (JSON)", readonly=True)
    currency_id = fields.Many2one(related="order_id.currency_id", readonly=True)
    product_price = fields.Float(related="product_tmpl_id.list_price", readonly=True)

    @api.depends("matched_keys", "mismatched_keys", "missing_keys")
    def _compute_display(self):
        for _rec in self:
            # Keep for future badge computation; no stored field now
            pass

    def action_add_to_order(self):
        self.ensure_one()
        order = self.order_id
        if self.product_id:
            product = self.product_id
        else:
            product = self.product_tmpl_id.product_variant_id
            if not product:
                # Create variant if needed - product template without variants
                product = self.env["product.product"].search(
                    [("product_tmpl_id", "=", self.product_tmpl_id.id)], limit=1
                )
        if not product:
            return False
        # Add as sale order line
        line_vals = {
            "order_id": order.id,
            "product_id": product.id,
            "product_uom_qty": 1,
        }
        # Let Odoo compute price/taxes via onchange
        line = self.env["sale.order.line"].create(line_vals)
        line.product_id_change()
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": order.id,
            "view_mode": "form",
            "target": "current",
        }

    def _get_matched_keys_list(self):
        self.ensure_one()
        try:
            return json.loads(self.matched_keys or "[]")
        except (ValueError, TypeError):
            return []

    def _get_mismatched_keys_list(self):
        self.ensure_one()
        try:
            return json.loads(self.mismatched_keys or "[]")
        except (ValueError, TypeError):
            return []
