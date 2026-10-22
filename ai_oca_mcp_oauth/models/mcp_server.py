# Copyright 2026 Quartile (https://www.quartile.co)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import secrets
from datetime import timedelta

import psycopg2

from odoo import api, fields, models
from odoo.tools import mute_logger

DEFAULT_TOKEN_LIFETIME_DAYS = 30


class McpServer(models.Model):
    _inherit = "mcp.server"

    oauth_enabled = fields.Boolean(
        string="OAuth",
        help="Let MCP clients such as Claude get a key for this server by having "
        "the user sign in to Odoo and approve the access, instead of entering "
        "a key by hand. Only users of the group 'Connect AI Clients with OAuth' "
        "can approve. Turning it off expires the keys clients got this way.",
    )

    def write(self, vals):
        if "oauth_enabled" in vals and not vals["oauth_enabled"]:
            # The users of OAuth keys are only checked while OAuth is enabled.
            self.key_ids.filtered("oauth_code_hash").expire_key()
        return super().write(vals)

    @api.model
    def _get_oauth_server(self, key):
        return self.sudo().search(
            [("key", "=", key), ("oauth_enabled", "=", True)], limit=1
        )

    def _get_oauth_metadata_url(self):
        """URL of the protected resource metadata (RFC 9728) of the server."""
        self.ensure_one()
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        return f"{base_url}/.well-known/oauth-protected-resource/mcp/{self.key}"

    @api.model
    def _is_oauth_user_allowed(self, user):
        user = user.sudo()
        return (
            user.active
            and user._is_internal()
            and user.has_group("ai_oca_mcp_oauth.group_mcp_oauth")
        )

    @api.model
    def _get_oauth_token_lifetime_days(self):
        return int(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "ai_oca_mcp_oauth.token_lifetime_days", DEFAULT_TOKEN_LIFETIME_DAYS
            )
        )

    def _oauth_issue_key(self, user, code, client_host):
        """Create the key an OAuth client gets for ``code``, return its token.

        A code gives one key only. When it comes back, it may have been stolen:
        return None and expire the key it gave (RFC 6749 4.1.2).
        """
        self.ensure_one()
        server_key_model = self.env["mcp.server.key"].sudo()
        code_hash = server_key_model._hash_key(code)
        used_key = server_key_model.search([("oauth_code_hash", "=", code_hash)])
        if used_key:
            used_key.expire_key()
            return None
        token = secrets.token_urlsafe(32)
        try:
            with self.env.cr.savepoint(), mute_logger("odoo.sql_db"):
                server_key_model.create(
                    {
                        "name": f"OAuth ({client_host})",
                        "server_id": self.id,
                        "user_id": user.id,
                        "hashed_key": server_key_model._hash_key(token),
                        "oauth_code_hash": code_hash,
                        "expiration_date": fields.Datetime.now()
                        + timedelta(days=self._get_oauth_token_lifetime_days()),
                    }
                )
        except psycopg2.IntegrityError:
            # Another request redeemed the same code at the same time.
            return None
        return token
