# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import json
import logging
from datetime import date, datetime

from odoo import _, api, fields, models
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


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
        [
            ("none", "None"),
            ("thread", "Thread"),
            ("ai_thread_create", "AI Thread Create"),
            ("ai_thread_write", "AI Thread Write"),
            ("ai_thread_unlink", "AI Thread Unlink"),
        ],
        default="none",
        help="Defines how this bridge is used. "
        "If 'Thread', it will be used in the mail thread context.",
    )
    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    description = fields.Html(translate=True)
    user_id = fields.Many2one(
        "res.users",
        default=lambda self: self.env.user,
        help="The user that will be shown when executing this AI bridge.",
    )
    payload_type = fields.Selection(
        [
            ("none", "No payload"),
            ("record", "Record"),
            ("record_v0", "Record v0"),  # Deprecated, use 'record' instead
        ],
        required=True,
        store=True,
        readonly=False,
        compute="_compute_payload_type",
        default="record",
    )
    result_type = fields.Selection(
        [
            ("none", "No processing"),
            ("message", "Post a Message"),
            ("action", "Action"),
        ],
        required=True,
        default="none",
        help="Defines the type of result expected from the AI system.",
    )
    result_kind = fields.Selection(
        [("immediate", "Immediate"), ("async", "Asynchronous")],
        default="immediate",
        help="""
        Defines how the result from the AI system is processed.
        - 'Immediate': The result is processed immediately after the AI system responds.
        - 'Asynchronous': The result is processed in the background.
          It allows longer operations.
          Odoo will provide a URL to the AI system where the response will be sent.
          Users will receive a notification when the operation is started.
          No notification will be sent when it is finished.
        """,
    )
    async_timeout = fields.Integer(
        default=300,
        help="Timeout in seconds for asynchronous operations. "
        "If the operation does not complete within this time, it will be considered failed.",
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
    auth_username = fields.Char(groups="base.group_system")
    auth_password = fields.Char(groups="base.group_system")
    auth_token = fields.Char(groups="base.group_system")
    group_ids = fields.Many2many(
        "res.groups",
        help="User groups allowed to use this AI bridge.",
    )
    sample_payload = fields.Text(
        help="Sample payload to be sent to the AI system. "
        "This is used for testing and debugging purposes.",
        compute="_compute_sample_payload",
    )
    model_id = fields.Many2one(
        "ir.model",
        string="Model",
        required=False,
        ondelete="cascade",
        help="The model to which this bridge is associated.",
    )
    model_required = fields.Boolean(compute="_compute_model_fields")

    #######################################
    # Payload type 'record' specific fields
    #######################################

    field_ids = fields.Many2many(
        "ir.model.fields",
        help="Fields to include in the AI bridge.",
        compute="_compute_field_ids",
        store=True,
        readonly=False,
    )
    model = fields.Char(
        related="model_id.model",
        string="Model Name",
    )
    domain = fields.Char(
        string="Filter", compute="_compute_domain", readonly=False, store=True
    )

    @api.onchange("usage")
    def _compute_payload_type(self):
        for record in self:
            if record.usage == "ai_thread_unlink":
                record.payload_type = "none"

    @api.constrains("usage", "payload_type")
    def _check_payload_type_usage_compatibility(self):
        for record in self:
            if record.usage == "ai_thread_unlink" and record.payload_type != "none":
                raise models.ValidationError(
                    _(
                        "When usage is 'AI Thread Unlink', "
                        "the Payload Type must be 'No payload'."
                    )
                )

    @api.depends("usage")
    def _compute_model_fields(self):
        for record in self:
            record.update(record._get_model_fields())

    def _get_model_fields(self):
        if self.usage == "thread":
            return {
                "model_required": True,
            }
        if self.usage in ["ai_thread_create", "ai_thread_write", "ai_thread_unlink"]:
            return {
                "model_required": True,
            }
        return {
            "model_required": False,
        }

    @api.depends("model_id")
    def _compute_domain(self):
        for record in self:
            record.domain = "[]"

    @api.depends("model_id")
    def _compute_field_ids(self):
        for record in self:
            record.field_ids = False

    @api.depends("field_ids", "model_id", "payload_type")
    def _compute_sample_payload(self):
        for record in self:
            record.sample_payload = json.dumps(
                record.with_context(sample_payload=True)._prepare_payload(), indent=4
            )

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
                    "model_id": self.sudo().env["ir.model"]._get_id(res_model),
                    "res_id": res_id,
                }
            )
            result = execution._execute()
            if result:
                return result
            if execution.state == "done":
                return {
                    "notification": {
                        "body": _("%s executed successfully.", self.name),
                        "args": {"type": "success", "title": _("AI Bridge Executed")},
                    }
                }
            return {
                "notification": {
                    "body": _("%s failed.", self.name),
                    "args": {"type": "danger", "title": _("AI Bridge Failed")},
                }
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

    def _prepare_payload(self, **kwargs):
        method = getattr(self, f"_prepare_payload_{self.payload_type}", None)
        if not method:
            raise ValueError(
                f"Unsupported payload type: {self.payload_type}. "
                "Please implement a method for this payload type."
            )
        return method(**kwargs)

    def _prepare_payload_none(self, res_model=False, res_id=False, **kwargs):
        return {
            "_model": res_model,
            "_id": res_id,
        }

    def _prepare_payload_record(self, record=None, **kwargs):
        """Prepare the payload to be sent to the AI system."""
        self.ensure_one()
        if not self.model_id:
            return {}
        if record is None and self.env.context.get("sample_payload"):
            record = self.env[self.model_id.model].search([], limit=1)
            if not record:
                return {}
        vals = {}
        if self.sudo().field_ids:
            vals = record.read(self.sudo().field_ids.mapped("name"))[0]
        return json.loads(
            json.dumps(
                {
                    "record": vals,
                    "_model": record._name,
                    "_id": record.id,
                },
                default=self.custom_serializer,
            )
        )

    def _prepare_payload_record_v0(self, record=None, **kwargs):
        """Prepare the payload to be sent to the AI system."""
        _logger.warning(
            "The 'record_v0' payload type is deprecated. " "Use 'record' instead."
        )
        self.ensure_one()
        if not self.model_id:
            return {}
        if record is None and self.env.context.get("sample_payload"):
            record = self.env[self.model_id.model].search([], limit=1)
            if not record:
                return {}
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
