# Copyright 2026 Sébastien Couratin, Semper Connect
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class OpenWebuiModel(models.Model):
    _name = "ai.openwebui.model"
    _description = "OpenWebUI Model"
    _order = "name, id"

    name = fields.Char(required=True)
    external_id = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)
    bridge_ids = fields.One2many("ai.bridge", "openwebui_model_id")

    _sql_constraints = [
        (
            "external_id_unique",
            "unique(external_id)",
            "The OpenWebUI model ID must be unique.",
        ),
    ]


class OpenWebuiTool(models.Model):
    _name = "ai.openwebui.tool"
    _description = "OpenWebUI Tool"
    _order = "name, id"

    name = fields.Char(required=True)
    external_id = fields.Char(required=True, index=True)
    description = fields.Text()
    active = fields.Boolean(default=True)
    bridge_ids = fields.Many2many("ai.bridge", string="Bridges")

    _sql_constraints = [
        (
            "external_id_unique",
            "unique(external_id)",
            "The OpenWebUI tool ID must be unique.",
        ),
    ]


# pylint: disable=consider-merging-classes-inherited
class AiBridge(models.Model):
    _inherit = "ai.bridge"

    openwebui_model_id = fields.Many2one(
        "ai.openwebui.model",
        string="OpenWebUI Model",
        ondelete="set null",
        help="Model selected from the models synchronized from OpenWebUI.",
    )
    openwebui_tool_record_ids = fields.Many2many(
        "ai.openwebui.tool",
        string="OpenWebUI Tools",
        help="Tools explicitly sent to OpenWebUI for this bridge.",
    )

    def action_openwebui_sync_catalog(self):
        for bridge in self:
            bridge._openwebui_sync_endpoint("/api/models", "models")
            bridge._openwebui_sync_endpoint("/api/v1/tools/", "tools")
        return True

    def _openwebui_sync_endpoint(self, path, kind):
        self.ensure_one()
        if not self.url:
            raise UserError(_("Set the OpenWebUI URL before synchronizing."))
        if not self.auth_token:
            raise UserError(_("Set the OpenWebUI API token before synchronizing."))
        base_url = self.url.split("/api/")[0].rstrip("/")
        response = requests.get(
            f"{base_url}{path}",
            headers={"Authorization": f"Bearer {self.auth_token}"},
            timeout=self.openwebui_timeout or 120,
        )
        response.raise_for_status()
        values = (
            response.json().get("data", []) if kind == "models" else response.json()
        )
        model = (
            self.env["ai.openwebui.model"]
            if kind == "models"
            else self.env["ai.openwebui.tool"]
        )
        for value in values:
            external_id = value.get("id")
            if not external_id:
                continue
            vals = {
                "name": value.get("name") or external_id,
                "external_id": external_id,
            }
            if kind == "tools":
                vals["description"] = value.get("meta", {}).get("description", "")
            record = model.search([("external_id", "=", external_id)], limit=1)
            if record:
                record.write(vals)
            else:
                model.create(vals)

    def _openwebui_tool_ids(self):
        self.ensure_one()
        selected = self.openwebui_tool_record_ids.mapped("external_id")
        return selected or super()._openwebui_tool_ids()

    @api.onchange("openwebui_model_id")
    def _onchange_openwebui_model_id(self):
        for bridge in self:
            if bridge.openwebui_model_id:
                bridge.openwebui_model = bridge.openwebui_model_id.external_id
