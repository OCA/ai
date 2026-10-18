# Copyright 2026 Quartile (https://www.quartile.co)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class McpServerKey(models.Model):
    _inherit = "mcp.server.key"

    oauth_code_hash = fields.Char(
        copy=False,
        readonly=True,
        help="Hash of the OAuth authorization code the key was issued for.",
    )

    _sql_constraints = [
        (
            "oauth_code_hash_uniq",
            "unique(oauth_code_hash)",
            "An authorization code gives one key only.",
        ),
    ]

    def action_disconnect(self):
        """Let users expire the keys their AI clients got through OAuth."""
        own_keys = self.filtered(
            lambda key: key.user_id == self.env.user and key.oauth_code_hash
        )
        own_keys.sudo().expire_key()
