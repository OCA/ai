# Copyright 2026 Coopdevs
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class AiToolRequestRecord(models.Model):
    _name = "ai.tool.request.record"
    _description = "Record created or modified by an AI tool request"
    _order = "id"

    # Security: as the request, readonly and without write or create access
    # for users: only the execution of an approved request fills it.
    request_id = fields.Many2one(
        "ai.tool.request", required=True, readonly=True, index=True, ondelete="cascade"
    )
    operation = fields.Selection(
        [("create", "Created"), ("write", "Modified")],
        required=True,
        readonly=True,
    )
    res_model = fields.Char(string="Model", required=True, readonly=True)
    res_id = fields.Many2oneReference(
        string="Record ID", model_field="res_model", required=True, readonly=True
    )
    record_ref = fields.Reference(
        selection="_selection_record_ref",
        string="Record",
        compute="_compute_record_ref",
    )

    @api.depends("res_model", "res_id")
    def _compute_record_ref(self):
        for line in self:
            if line.res_model in self.env and line.res_id:
                line.record_ref = f"{line.res_model},{line.res_id}"
            else:
                line.record_ref = False

    @api.model
    def _selection_record_ref(self):
        return self.env["ai.tool.request"]._selection_record_ref()
