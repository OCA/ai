# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class IrModelFields(models.Model):
    _inherit = "ir.model.fields"

    ttype = fields.Selection(
        selection_add=[("computed_vector", "Vector with automatic filling")],
        ondelete={"computed_vector": "cascade"},
    )
    vector_configuration_ids = fields.One2many(
        "ir.model.field.vector",
        inverse_name="field_id",
    )
