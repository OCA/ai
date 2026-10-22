# Copyright 2026 Quartile (https://www.quartile.co)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import SUPERUSER_ID, api


def uninstall_hook(cr, registry):
    """Expire the keys from OAuth: without this module, nothing checks their
    users any more."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["mcp.server.key"].search([("oauth_code_hash", "!=", False)]).expire_key()
