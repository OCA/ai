# Copyright 2026 Coopdevs
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from contextvars import ContextVar

from odoo import api, fields, models
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)

# Security: these flags live in context variables, not in the Odoo context.
# The Odoo context travels with every RPC call, so any client could set a
# context key; a context variable can only be set by server-side code.
#
# Id of the tool an approved request is executing right now: the only way to
# run a tool that requires confirmation.
approved_tool = ContextVar("ai_tool_confirm_approved_tool", default=None)
# True while any AI tool is running: an AI tool must never answer a request,
# or an LLM could approve its own actions.
running_tool = ContextVar("ai_tool_confirm_running_tool", default=False)
# The approved request being executed right now (an ApprovedExecution).
# Audit: records created or modified meanwhile are linked to it and say so in
# their chatter.
executing_request = ContextVar("ai_tool_confirm_executing_request", default=None)


class ApprovedExecution:
    """What an approved request does while it runs, for the audit trail."""

    def __init__(self, request):
        # The request in the environment of its approver, whatever the
        # environment the tool creates or modifies records in.
        self.request = request
        # {(model, id)} of the records created
        self.created = set()
        # {(model, id): {field: value before the first write}}
        self.initial_values = {}


class AiTool(models.Model):
    _inherit = "ai.tool"

    confirmation = fields.Selection(
        [
            ("default", "When the tool modifies data"),
            ("always", "Always"),
            ("never", "Never"),
        ],
        string="Human Confirmation",
        required=True,
        default="default",
        help="When a human must confirm a call to this tool before it is "
        "executed. By default, every tool not flagged as read-only.",
    )
    requires_confirmation = fields.Boolean(compute="_compute_requires_confirmation")

    @api.depends("confirmation", "read_only")
    def _compute_requires_confirmation(self):
        for tool in self:
            if tool.confirmation == "default":
                tool.requires_confirmation = not tool.read_only
            else:
                tool.requires_confirmation = tool.confirmation == "always"

    def write(self, vals):
        # Security: administrators get write access to decide on confirmation
        # only. What a tool executes (model, function, kind, read-only flag)
        # stays defined by code: data files are loaded as superuser.
        if not self.env.su and set(vals) - {"confirmation"}:
            raise AccessError(
                self.env._("Only the human confirmation of AI tools can be changed.")
            )
        if "confirmation" in vals:
            # Audit: disabling the confirmation of a tool must leave a trace
            _logger.info(
                "AI tools %s: human confirmation set to %r by user %s",
                self.ids,
                vals["confirmation"],
                self.env.uid,
            )
        return super().write(vals)

    def _execute_tool(self, *args, record=None, **kwargs):
        token = running_tool.set(True)
        try:
            if not self.requires_confirmation:
                return super()._execute_tool(*args, record=record, **kwargs)
            if approved_tool.get() != self.id:
                return self._request_confirmation(args, kwargs, record)
            # Security: an approval is good for one execution. If the tool
            # runs an LLM itself (nested agents), that LLM calling this same
            # tool again needs a confirmation of its own.
            consumed = approved_tool.set(None)
            try:
                return super()._execute_tool(*args, record=record, **kwargs)
            finally:
                approved_tool.reset(consumed)
        finally:
            running_tool.reset(token)

    def _get_model_name(self):
        """Technical name of the model of the tool.

        Security: sudo, because users cannot read ir.model. It only reads
        metadata (a model name), not data.
        """
        self.ensure_one()
        return self.sudo().model_id.model

    def _describe_call(self, arguments, record=None):
        """Describe a call to this tool for the person who must approve it.

        A tool can explain its calls in plain words with a method named after
        its function plus ``_describe``, taking the same arguments and
        returning a string. It is called on the same target as the tool
        function, with the access rights of the person reading the request.
        It must only read data: it runs every time the request is displayed.
        Security: this is not enforced (rolling back a savepoint would also
        drop the pending tracking of the whole transaction); a describe
        method is code of the tool, as trusted as the tool function itself.
        Security: its arguments are NOT trusted: an LLM wrote them, and it
        runs with the rights of whoever opens the request, an administrator
        included. Never use them to pick a model, a method or a field.

        :return: the description, or None when the tool does not provide one
        """
        self.ensure_one()
        model = self._get_model_name()
        method_name = f"{self.function_name}_describe"
        if self.kind == "record":
            target = record
        else:
            target = self.env[model]
        if target is None or not hasattr(target, method_name):
            return None
        if self.kind == "generic_model":
            arguments = dict(arguments, record=record)
        return getattr(target, method_name)(**arguments)

    def _ai_post_message_describe(self, message=None, record=None, **kwargs):
        return self.env._(
            "Post a message on %(record)s:\n\n%(message)s",
            record=record.display_name if record else "?",
            message=message,
        )

    def _request_confirmation(self, args, kwargs, record):
        """Instead of executing the tool, ask a human to confirm the call."""
        self.ensure_one()
        if args:
            raise ValueError(
                "Tools that require confirmation only accept keyword arguments"
            )
        # Security: callers such as MCP clients pass their arguments straight
        # through; make sure "record" is a real record before trusting it.
        if record is not None and not isinstance(record, models.BaseModel):
            raise ValueError("The record of an AI tool call must be an Odoo record")
        request = self.env["ai.tool.request"]._create_from_tool_call(
            self, kwargs, record=record
        )
        return request._get_pending_response()
