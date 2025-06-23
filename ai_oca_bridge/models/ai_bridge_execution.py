# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import traceback
from datetime import timedelta
from io import StringIO

import requests
from werkzeug import urls

from odoo import _, api, fields, models, tools


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
    res_id = fields.Integer(required=False)
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
        required=False,
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
    expiration_date = fields.Datetime(
        readonly=True,
        help="Expiration date for the async operation token.",
    )

    @api.depends("model_id", "res_id", "ai_bridge_id")
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

    def _add_extra_payload_fields(self, payload):
        """Add extra fields to the payload if needed."""
        self.ensure_one()
        if self.ai_bridge_id.result_kind == "async":
            self.expiration_date = fields.Datetime.now() + timedelta(
                seconds=self.ai_bridge_id.async_timeout
            )
            token = self._generate_token()
            payload["_response_url"] = urls.url_join(
                self.get_base_url(), f"/ai/response/{self.id}/{token}"
            )
        IrParamSudo = self.env["ir.config_parameter"].sudo()
        dbuuid = IrParamSudo.get_param("database.uuid")
        db_create_date = IrParamSudo.get_param("database.create_date")
        payload["_odoo"] = {
            "db": dbuuid,
            "db_name": self.env.cr.dbname,
            "db_hash": tools.hmac(
                self.env(su=True),
                "database-hash",
                (dbuuid, db_create_date, self.env.cr.dbname),
            ),
            "user_id": self.env.user.id,
        }
        return payload

    def _execute(self, **kwargs):
        self.ensure_one()
        record = None
        if self.res_id and self.model_id:
            record = self.env[self.sudo().model_id.model].browse(self.res_id)
        payload = self.ai_bridge_id._prepare_payload(
            record=record,
            res_id=self.res_id,
            model=self.sudo().model_id.model,
            **kwargs,
        )
        payload = self._add_extra_payload_fields(payload)
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
            if self.ai_bridge_id.result_kind == "immediate":
                return self._process_response(response.json())
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

    def _generate_token(self):
        """Generate a token for async operations."""
        self.ensure_one()
        return tools.hmac(
            self.env(su=True),
            "ai_bridge-access_token",
            (
                self.id,
                self.expiration_date and self.expiration_date.isoformat() or "expired",
            ),
        )

    def _process_response(self, response):
        """Process the response from the AI bridge."""
        self.ensure_one()
        self.expiration_date = None
        return getattr(
            self.with_user(self.ai_bridge_id.user_id.id),
            f"_process_response_{self.ai_bridge_id.result_type}",
            self._process_response_none,
        )(response)

    def _process_response_none(self, response):
        return {}

    def _process_response_message(self, response):
        return {"id": self._get_channel().message_post(**response).id}

    def _process_response_action(self, response):
        if response.get("action"):
            action = self.env["ir.actions.actions"]._for_xml_id(response["action"])
            if response.get("context"):
                action["context"] = response["context"]
            if response.get("res_id"):
                action["res_id"] = response["res_id"]
            return {"action": action}
        return {}

    def _get_channel(self):
        if self.model_id and self.res_id:
            return self.env[self.model_id.model].browse(self.res_id)
        return None
