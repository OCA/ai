# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import traceback
from io import StringIO

import requests

from odoo import _, api, fields, models


class AiBridgeExecution(models.Model):

    _name = "ai.bridge.execution"
    _description = "Ai Execution"
    _order = "id desc"

    name = fields.Char(
        store=True,
        compute="_compute_name",
    )

    ai_bridge_id = fields.Many2one(
        "ai.bridge",
        required=True,
        ondelete="cascade",
    )
    res_id = fields.Integer(required=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("done", "Done"),
            ("error", "Error"),
        ],
        default="draft",
        required=True,
    )
    model_id = fields.Many2one(
        "ir.model",
        required=True,
        ondelete="cascade",
    )
    payload = fields.Json(readonly=True)
    payload_txt = fields.Text(
        compute="_compute_payload_txt",
    )
    result = fields.Text(readonly=True)
    error = fields.Text(readonly=True)
    company_id = fields.Many2one(
        "res.company",
        compute="_compute_company_id",
        store=True,
        readonly=True,
    )

    @api.depends()
    def _compute_name(self):
        for record in self:
            model = record.sudo().model_id.name or "Unknown Model"
            related = self.env[record.sudo().model_id.model].browse(record.res_id)
            record.name = (
                f"{model} - {related.display_name} - {record.ai_bridge_id.name}"
            )

    @api.depends("payload")
    def _compute_payload_txt(self):
        for record in self:
            if record.payload:
                try:
                    record.payload_txt = json.dumps(record.payload, indent=4)
                except (TypeError, ValueError):
                    record.payload_txt = str(record.payload)
            else:
                record.payload_txt = ""

    @api.depends("ai_bridge_id")
    def _compute_company_id(self):
        for record in self:
            record.company_id = record.ai_bridge_id.company_id

    def _execute(self, **kwargs):
        self.ensure_one()
        payload = self.ai_bridge_id._prepare_payload(
            self.env[self.sudo().model_id.model].browse(self.res_id), **kwargs
        )
        try:
            response = requests.post(
                self.ai_bridge_id.url,
                json=payload,
                auth=self._get_auth(),
                headers=self._get_headers(),
                timeout=30,  # Default timeout, can be overridden by _execute_kwargs
                **self._execute_kwargs(**kwargs),
            )
            self.result = response.content
            response.raise_for_status()
            self.state = "done"
            self.payload = payload
        except Exception:
            self.state = "error"
            self.payload = payload
            buff = StringIO()
            traceback.print_exc(file=buff)
            self.error = buff.getvalue()
            buff.close()

    def _execute_kwargs(self, timeout=False, **kwargs):
        self.ensure_one()
        result = {}
        if timeout:
            result["timeout"] = timeout
        return result

    def _get_auth(self):
        """Return authentication for the request."""
        if self.ai_bridge_id.auth_type == "none":
            return None
        elif self.ai_bridge_id.auth_type == "basic":
            return (
                self.ai_bridge_id.sudo().auth_username,
                self.ai_bridge_id.sudo().auth_password,
            )
        elif self.ai_bridge_id.auth_type == "token":
            return {"Authorization": f"Bearer {self.ai_bridge_id.sudo().auth_token}"}
        else:
            raise ValueError(_("Unsupported authentication type."))

    def _get_headers(self):
        """Return headers for the request."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
