# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class AiMessageImportOrderConfirm(models.TransientModel):
    """Warn before confirming an order with open document incidents."""

    _name = "ai.message.import.order.confirm"
    _description = "Confirm an Order with Open Incidents"

    res_model = fields.Char(required=True)
    res_id = fields.Many2oneReference(model_field="res_model", required=True)
    incident_summary = fields.Text(compute="_compute_incidents")
    incident_count = fields.Integer(compute="_compute_incidents")

    def _get_order(self):
        self.ensure_one()
        return self.env[self.res_model].browse(self.res_id)

    @api.depends("res_model", "res_id")
    def _compute_incidents(self):
        for wizard in self:
            order = wizard._get_order() if wizard.res_model and wizard.res_id else None
            wizard.incident_summary = (
                order.ai_message_import_open_incident_summary if order else ""
            )
            wizard.incident_count = (
                order.ai_message_import_open_incident_count if order else 0
            )

    def action_confirm(self):
        return self._get_order()._ai_message_confirm()
