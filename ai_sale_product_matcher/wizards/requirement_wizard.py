# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo import fields, models
from odoo.exceptions import UserError


class AiSaleRequirementWizard(models.TransientModel):
    _name = "ai.sale.requirement.wizard"
    _description = "AI Requirement Wizard"

    order_id = fields.Many2one("sale.order", required=True, readonly=True)
    requirement_text = fields.Text(
        string="Requirement Text", help="Paste email, spec sheet text, etc."
    )
    requirements_json = fields.Text(
        string="Extracted Requirements (JSON)", help="Edit before matching"
    )
    ai_connection_id = fields.Many2one(
        "ai.connection", string="AI Connection", required=True
    )
    state = fields.Selection(
        [("draft", "Draft"), ("extracting", "Extracting"), ("done", "Done")],
        default="draft",
        readonly=True,
    )
    attachment_ids = fields.Many2many("ir.attachment", string="Requirement Files")
    # Optional filters — sector-independent: filter matching within selected brand/category
    brand_id = fields.Many2one(
        "product.category",
        string="Brand",
        help="Optional: limit matching to this brand (top-level category like Nilfisk/Viper/Rottest)",
        domain="[('parent_id', '=', False)]",
    )
    categ_id = fields.Many2one(
        "product.category",
        string="Category",
        help="Optional: limit matching to this category",
        domain="[('parent_id', '!=', False)]",
    )
    match_ids = fields.One2many(
        related="order_id.ai_match_ids", string="Matches", readonly=True
    )

    def action_extract(self):
        self.ensure_one()
        if not self.attachment_ids and not (self.requirement_text or "").strip():
            raise UserError(self.env._("Attach a file or enter requirement text."))
        # Trigger extraction on order
        self.order_id.write({"ai_connection_id": self.ai_connection_id.id})
        self.order_id.action_extract_requirements(
            attachment_ids=self.attachment_ids.ids,
            requirement_text=self.requirement_text or "",
        )
        self.state = "extracting"
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_refresh(self):
        self.ensure_one()
        # Pull latest from order
        self.requirements_json = self.order_id.ai_requirement_json or ""
        self.state = (
            "done" if self.order_id.ai_requirement_state == "done" else self.state
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_match(self):
        self.ensure_one()
        # Save edited JSON to order and run matching
        if (self.requirements_json or "").strip():
            try:
                data = json.loads(self.requirements_json)
                if not isinstance(data, dict):
                    raise ValueError("Requirements must be a JSON object")
                # Validate keys quickly
                from ..services.catalog_schema import get_attribute_meta

                cleaned = {}
                for k, v in data.items():
                    if v is None:
                        continue
                    if get_attribute_meta(k, env=self.env):
                        cleaned[k] = v
                self.order_id.write(
                    {
                        "ai_requirement_json": json.dumps(
                            cleaned, ensure_ascii=False, indent=2
                        )
                    }
                )
            except Exception as e:
                raise UserError(self.env._("Invalid JSON: %s", str(e))) from e
        # Pass optional brand/category filters to matching (sector-independent)
        self.order_id.write(
            {
                "ai_filter_brand_id": self.brand_id.id or False,
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

    def action_add_selected(self):
        self.ensure_one()
        # Add all matches with weighted_percent >= threshold? For now add top 1
        if not self.order_id.ai_match_ids:
            raise UserError(self.env._("No matches found. Run Find Matches first."))
        # Let user add via match lines actions; close wizard
        return {"type": "ir.actions.act_window_close"}
