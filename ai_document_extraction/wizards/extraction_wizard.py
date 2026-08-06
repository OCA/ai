# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ExtractionWizard(models.TransientModel):
    _name = "extraction.wizard"
    _description = "Review AI Extraction"

    move_id = fields.Many2one(
        "account.move",
        string="Invoice",
        required=True,
        readonly=True,
    )
    extracted_partner_name = fields.Char(readonly=True)
    partner_id = fields.Many2one("res.partner")

    def action_apply(self):
        self.ensure_one()
        move = self.move_id
        if move.state != "draft":
            return {"type": "ir.actions.act_window_close"}
        move.write(
            {
                "partner_id": self.partner_id.id,
                "ai_extraction_state": "done",
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": move.id,
            "view_mode": "form",
        }
