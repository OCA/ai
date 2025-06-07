# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import json
from datetime import date, datetime

from odoo import _, api, fields, models
from odoo.tools.safe_eval import safe_eval


class AiBridge(models.Model):

    _name = "ai.bridge"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Ai Bridge Configuration"
    _order = "sequence, id"

    sequence = fields.Integer(
        default=10,
    )
    company_id = fields.Many2one(
        "res.company",
        # We leave it empty to allow multiple companies to use the same bridge.
    )
    usage = fields.Selection(
        [("none", "None"), ("thread", "Thread")],
        default="none",
        help="Defines how this bridge is used. "
        "If 'Thread', it will be used in the mail thread context.",
    )
    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    description = fields.Html(translate=True)
    model_id = fields.Many2one(
        "ir.model",
        string="Model",
        domain=[("transient", "=", False)],
        required=True,
        ondelete="cascade",
        help="The model to which this bridge is associated.",
    )
    model = fields.Char(
        related="model_id.model",
        string="Model Name",
    )
    domain = fields.Char(
        string="Filter", compute="_compute_domain", readonly=False, store=True
    )
    execution_ids = fields.One2many("ai.bridge.execution", "ai_bridge_id")
    execution_count = fields.Integer(
        compute="_compute_execution_count",
    )
    url = fields.Char(
        string="URL",
        help="The URL of the external AI system to which this bridge connects.",
    )
    auth_type = fields.Selection(
        selection=[
            ("none", "None"),
            ("basic", "Basic Authentication"),
            ("token", "Token Authentication"),
        ],
        default="none",
        string="Authentication Type",
        help="The type of authentication used to connect to the external AI system.",
    )
    group_ids = fields.Many2many(
        "res.groups",
        help="User groups allowed to use this AI bridge.",
    )
    field_ids = fields.Many2many(
        "ir.model.fields",
        help="Fields to include in the AI bridge.",
        compute="_compute_field_ids",
        store=True,
        readonly=False,
    )
    auth_username = fields.Char(groups="base.group_system")
    auth_password = fields.Char(groups="base.group_system")
    auth_token = fields.Char(groups="base.group_system")
    sample_payload = fields.Text(
        help="Sample payload to be sent to the AI system. "
        "This is used for testing and debugging purposes.",
        compute="_compute_sample_payload",
    )

    @api.depends("model_id")
    def _compute_domain(self):
        for record in self:
            record.domain = "[]"

    @api.depends("model_id")
    def _compute_field_ids(self):
        for record in self:
            record.field_ids = False

    @api.depends("field_ids", "model_id")
    def _compute_sample_payload(self):
        for record in self:
            if not record.model_id:
                record.sample_payload = json.dumps({})
                continue
            item = record.env[record.model_id.model].search([], limit=1)
            if item:
                record.sample_payload = json.dumps(
                    record._prepare_payload(item), indent=4
                )
            else:
                record.sample_payload = json.dumps({})

    @api.depends("execution_ids")
    def _compute_execution_count(self):
        for record in self:
            record.execution_count = len(record.execution_ids)

    def _get_info(self):
        return {"id": self.id, "name": self.name, "description": self.description}

    def execute_ai_bridge(self, res_model, res_id):
        self.ensure_one()
        if not self.active or (
            self.group_ids and not self.env.user.groups_id & self.group_ids
        ):
            return {
                "body": _("%s is not active.", self.name),
                "args": {"type": "warning", "title": _("AI Bridge Inactive")},
            }
        record = self.env[res_model].browse(res_id).exists()
        if record:
            execution = self.env["ai.bridge.execution"].create(
                {
                    "ai_bridge_id": self.id,
                    "model_id": self.sudo().model_id.id,
                    "res_id": res_id,
                }
            )
            execution._execute()
            if execution.state == "done":
                return {
                    "body": _("%s executed successfully.", self.name),
                    "args": {"type": "success", "title": _("AI Bridge Executed")},
                }
            return {
                "body": _("%s failed.", self.name),
                "args": {"type": "danger", "title": _("AI Bridge Failed")},
            }

    def _enabled_for(self, record):
        """Check if the bridge is enabled for the given record."""
        self.ensure_one()
        domain = safe_eval(self.domain)
        if self.group_ids and not self.env.user.groups_id & self.group_ids:
            return False
        if domain:
            return bool(record.filtered_domain(domain))
        return True

    def _prepare_payload(self, record, **kwargs):
        """Prepare the payload to be sent to the AI system."""
        self.ensure_one()
        vals = {}
        if self.sudo().field_ids:
            vals = record.read(self.sudo().field_ids.mapped("name"))[0]
        return json.loads(
            json.dumps(
                {
                    **vals,
                    "_model": record._name,
                    "_id": record.id,
                },
                default=self.custom_serializer,
            )
        )

    def custom_serializer(self, obj):
        if isinstance(obj, datetime) or isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return base64.b64encode(obj).decode("utf-8")
        raise TypeError(f"Type {type(obj)} not serializable")
