from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = "res.users"

    vapi_api_key = fields.Char("User Vapi API Key", copy=False, index=True)

    _sql_constraints = [
        ("vapi_api_key_unique", "unique(vapi_api_key)", _("User Vapi API Key must be unique for each user.")),
    ]

    @api.constrains("vapi_api_key")
    def _check_vapi_api_key(self):
        for user in self:
            if user.vapi_api_key:
                users = self.search([
                    ("vapi_api_key", "=", user.vapi_api_key),
                    ("id", "!=", user.id)
                ])
                if users:
                    raise ValidationError(_("User Vapi API Key must be unique for each user."))

