# Copyright 2026-TODAY Akretion - Raphael Valyi <raphael.valyi@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import secrets

from odoo import _, api, fields, models


class HermesGateway(models.Model):
    _name = "hermes.gateway"
    _description = "Hermes Gateway Configuration"
    _inherit = ["mail.thread"]

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    odoo_url = fields.Char(
        string="Odoo Base URL",
        default=lambda self: (
            self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        ),
        help="The base URL of this Odoo instance that Hermes will connect to.",
    )
    webhook_token = fields.Char(
        default=lambda self: secrets.token_hex(32),
        groups="base.group_system",
        help="Secret token shared with the Hermes gateway for authentication.",
        readonly=True,
        copy=False,
    )
    hermes_url = fields.Char(
        string="Hermes URL",
        help="URL of the Hermes gateway (optional, for reference).",
    )
    channel_ids = fields.Many2many(
        "discuss.channel",
        string="Monitored Channels",
        help="Channels where Hermes will respond. Leave empty to monitor all channels.",
    )
    ai_user_id = fields.Many2one(
        "res.users",
        string="AI User",
        required=True,
        domain=[("ai_bridge_id", "!=", False)],
        help="The Odoo user that Hermes will post responses as.",
    )
    state = fields.Selection(
        [("draft", "Draft"), ("connected", "Connected"), ("error", "Error")],
        default="draft",
    )
    last_poll = fields.Datetime(readonly=True)
    message_count = fields.Integer(compute="_compute_message_count")
    mode = fields.Selection(
        [
            ("polling", "Polling (pull)"),
            ("webhook", "Webhook (push)"),
        ],
        default="polling",
        required=True,
        help="How Hermes connects to Odoo. "
        "Polling = Hermes polls Odoo. "
        "Webhook = Odoo pushes to Hermes.",
    )
    gateway_version = fields.Char(
        help="Version of the Hermes gateway script (for compatibility checks).",
    )
    last_error = fields.Text(readonly=True)
    last_error_date = fields.Datetime(readonly=True)

    @api.depends("message_count")
    def _compute_message_count(self):
        for gateway in self:
            gateway.message_count = self.env["hermes.message.queue"].search_count(
                [("gateway_id", "=", gateway.id)]
            )

    def action_regenerate_token(self):
        """Generate a new webhook token (invalidates old one)."""
        for gateway in self:
            gateway.webhook_token = secrets.token_hex(32)

    def action_test_connection(self):
        """Test connectivity by polling the gateway health endpoint."""
        self.ensure_one()
        if not self.hermes_url:
            return self._notify(_("No Hermes URL configured"), "warning")
        try:
            import requests

            resp = requests.get(
                f"{self.hermes_url}/health",
                timeout=5,
                headers={"Authorization": f"Bearer {self.webhook_token}"},
            )
            if resp.status_code == 200:
                self.state = "connected"
                return self._notify(_("Connection successful!"), "success")
            else:
                self.state = "error"
                return self._notify(f"HTTP {resp.status_code}", "error")
        except Exception as e:
            self.state = "error"
            return self._notify(str(e), "error")

    def _notify(self, message, type_="info"):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": "Hermes Gateway", "message": message, "type": type_},
        }
