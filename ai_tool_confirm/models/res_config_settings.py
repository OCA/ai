# Copyright 2026 Coopdevs
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import math

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .ai_tool_request import DEFAULT_EXPIRATION_HOURS, DEFAULT_MAX_PENDING_PER_HOUR


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    ai_tool_confirm_expiration_hours = fields.Float(
        string="AI Confirmation Expiration (hours)",
        config_parameter="ai_tool_confirm.expiration_hours",
        default=DEFAULT_EXPIRATION_HOURS,
        help="Hours a pending AI tool request can wait for confirmation. "
        "Use 0 for requests that never expire.",
    )
    ai_tool_confirm_fallback_approver_id = fields.Many2one(
        "res.users",
        string="AI Confirmation Fallback Approver",
        config_parameter="ai_tool_confirm.fallback_approver_id",
        domain=[("share", "=", False)],
        help="Approver of the AI tool requests with no person behind "
        "(scheduled actions, job queues, webhooks) on records without a "
        "responsible user.",
    )

    ai_tool_confirm_max_pending_per_hour = fields.Integer(
        string="AI Confirmation Limit (per hour)",
        config_parameter="ai_tool_confirm.max_pending_per_hour",
        default=DEFAULT_MAX_PENDING_PER_HOUR,
        help="Pending AI tool requests a user can receive in an hour. Beyond "
        "it, new requests are refused, so that nobody gets flooded. Use 0 "
        "for no limit.",
    )

    @api.constrains("ai_tool_confirm_max_pending_per_hour")
    def _check_ai_tool_confirm_max_pending_per_hour(self):
        for settings in self:
            if settings.ai_tool_confirm_max_pending_per_hour < 0:
                raise ValidationError(
                    self.env._("The AI confirmation limit must be 0 or more.")
                )

    @api.constrains("ai_tool_confirm_expiration_hours")
    def _check_ai_tool_confirm_expiration_hours(self):
        # A wrong value would make every AI tool that modifies data fail
        for settings in self:
            hours = settings.ai_tool_confirm_expiration_hours
            if not math.isfinite(hours) or hours < 0:
                raise ValidationError(
                    self.env._("The AI confirmation expiration must be 0 or more.")
                )
