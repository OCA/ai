# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo import fields, models
from odoo.exceptions import UserError

from ..services.catalog_schema import get_attribute_meta


class AiSaleRequirementWizard(models.TransientModel):
    _name = "ai.sale.requirement.wizard"
    _description = "AI Requirement Wizard"

    order_id = fields.Many2one("sale.order", required=True, readonly=True)
    requirement_text = fields.Text(help="Paste email, specification sheet text, etc.")
    requirements_json = fields.Text(
        string="Extracted Requirements (JSON)",
        help="Review or edit extracted requirements before matching.",
    )
    ai_connection_id = fields.Many2one(
        "ai.connection", string="AI Connection", required=False
    )
    state = fields.Selection(
        [("draft", "Draft"), ("extracting", "Extracting"), ("done", "Done")],
        default="draft",
        readonly=True,
    )
    attachment_ids = fields.Many2many("ir.attachment", string="Requirement Files")
    categ_id = fields.Many2one(
        "product.category",
        string="Category",
        help="Optional: limit matching to this product category and its subcategories.",
    )
    match_ids = fields.One2many(
        related="order_id.ai_match_ids", string="Matches", readonly=True
    )

    def action_extract(self):
        self.ensure_one()
        if not self.attachment_ids and not (self.requirement_text or "").strip():
            raise UserError(self.env._("Attach a file or enter requirement text."))
        connection = self.ai_connection_id or self.order_id._get_ai_connection()
        if not connection:
            raise UserError(
                self.env._(
                    "No AI Connection configured. Set one in the wizard or "
                    "Sales Settings."
                )
            )
        self.order_id.write({"ai_connection_id": connection.id})
        self.order_id.action_extract_requirements(
            attachment_ids=self.attachment_ids.ids,
            requirement_text=self.requirement_text or "",
        )
        self.requirements_json = self.order_id.ai_requirement_json or ""
        self.state = "done" if self.order_id.ai_requirement_state == "done" else "draft"
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_match(self):
        self.ensure_one()
        if (self.requirements_json or "").strip():
            try:
                data = json.loads(self.requirements_json)
                if not isinstance(data, dict):
                    raise ValueError("Requirements must be a JSON object")
                cleaned = {}
                for key, val in data.items():
                    if val is None:
                        continue
                    if get_attribute_meta(key, env=self.env):
                        cleaned[key] = val
                self.order_id.write(
                    {
                        "ai_requirement_json": json.dumps(
                            cleaned, ensure_ascii=False, indent=2
                        )
                    }
                )
            except Exception as err:
                raise UserError(self.env._("Invalid JSON: %s", str(err))) from err
        self.order_id.write(
            {
                "ai_filter_categ_id": self.categ_id.id or False,
            }
        )
        self.order_id._ai_run_matching()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
