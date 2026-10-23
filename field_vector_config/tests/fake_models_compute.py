# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

from odoo.addons.field_vector_config.fields import ComputedVector


class VectorFakeModel(models.Model):
    _name = "vector.fake.model"
    _description = "Fake model to test vector configuration"

    name = fields.Char()
    partner_id = fields.Many2one("res.partner")
    description_vector = ComputedVector(
        compute="_compute_description_vector", store=True
    )

    @api.depends("name")
    def _compute_description_vector(self):
        for record in self:
            record.description_vector = record._encode_vector(
                "description_vector", record.name or ""
            )[0]
