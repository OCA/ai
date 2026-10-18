# Copyright 2026 Quartile (https://www.quartile.co)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    mcp_oauth_key_ids = fields.One2many(
        "mcp.server.key",
        "user_id",
        string="AI Clients",
        domain=lambda self: self._get_mcp_oauth_key_domain(),
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ["mcp_oauth_key_ids"]

    def _get_mcp_oauth_key_domain(self):
        # A key past its expiration date may still be "active": its state only
        # changes when a client uses it.
        return [
            ("oauth_code_hash", "!=", False),
            ("state", "=", "active"),
            ("expiration_date", ">", fields.Datetime.now()),
        ]
