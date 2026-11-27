# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    channel_type = fields.Selection(
        selection_add=[("ai_agent", "AI Agent Conversation")],
        ondelete={"ai_agent": "cascade"},
    )
    ai_agent_id = fields.Many2one(
        "ai.agent",
        string="AI Agent",
        index="btree_not_null",
        ondelete="cascade",
        readonly=True,
    )
    ai_res_model = fields.Char(
        string="Context Model",
        readonly=True,
        help="Model of the document this AI agent conversation is about.",
    )
    ai_res_id = fields.Integer(string="Context Record ID", readonly=True)
    ai_context = fields.Json(
        string="View Context",
        readonly=True,
        help="The view the user was looking at when starting the conversation: "
        "action, view type, domain, groupings and filters.",
    )
    ai_res_display_name = fields.Char(
        compute="_compute_ai_res_display_name",
        string="Context Document",
    )

    @api.depends("ai_res_model", "ai_res_id")
    @api.depends_context("uid")
    def _compute_ai_res_display_name(self):
        for channel in self:
            document = channel._ai_get_context_document()
            channel.ai_res_display_name = document.display_name if document else False

    def _ai_get_context_document(self):
        """The context document, read with the rights of the current user.

        Empty when there is none, it no longer exists or it is not readable.
        """
        self.ensure_one()
        if not self.ai_res_model or self.ai_res_model not in self.env:
            return None
        document = self.env[self.ai_res_model].browse(self.ai_res_id).exists()
        if not document:
            return None
        try:
            document.check_access("read")
        except AccessError:
            return None
        return document

    def _ai_context_description(self):
        """The context of the conversation, described to the AI."""
        self.ensure_one()
        if not self.ai_res_model or self.ai_res_model not in self.env:
            return False
        context = self.ai_context or {}
        model_name = self.env[self.ai_res_model]._description
        lines = []
        document = self._ai_get_context_document()
        if document:
            lines.append(
                self.env._(
                    "This conversation is about the document %(name)s "
                    "(%(model_name)s, model %(model)s, id %(id)s).",
                    name=document.display_name,
                    model_name=model_name,
                    model=document._name,
                    id=document.id,
                )
            )
        if context.get("view_type"):
            lines.append(
                self.env._(
                    "The user started it from the %(view_type)s view of "
                    '"%(action)s" (%(model_name)s, model %(model)s).',
                    view_type=context["view_type"],
                    action=context.get("action_name") or model_name,
                    model_name=model_name,
                    model=self.ai_res_model,
                )
            )
        elif not document:
            lines.append(
                self.env._(
                    "This conversation is about %(model_name)s (model %(model)s).",
                    model_name=model_name,
                    model=self.ai_res_model,
                )
            )
        if context.get("facets"):
            lines.append(
                self.env._("Active filters: %s.", "; ".join(context["facets"]))
            )
        if context.get("group_by"):
            lines.append(self.env._("Grouped by: %s.", ", ".join(context["group_by"])))
        if context.get("domain"):
            lines.append(
                self.env._(
                    "Domain of the records shown: %s", json.dumps(context["domain"])
                )
            )
        return "\n".join(lines)

    @api.constrains("channel_member_ids", "channel_type")
    def _constraint_ai_agent_chat(self):
        if self.env.context.get("ai_agent_allow_dm"):
            return
        agent_partners = self.env["ai.agent"]._ai_get_agent_partners()
        # sudo: discuss.channel - only reading the members of the channel
        chats = self.sudo().filtered(lambda ch: ch.channel_type == "chat")
        if any(chat.channel_partner_ids & agent_partners for chat in chats):
            raise ValidationError(
                self.env._(
                    "AI agents can not receive direct messages: start a "
                    "conversation with the agent instead."
                )
            )

    @api.model
    def channel_get(self, partners_to, pin=True, force_open=False):
        if not self.env.context.get("ai_agent_allow_dm"):
            agent_partners = self.env["ai.agent"]._ai_get_agent_partners()
            if set(partners_to) & set(agent_partners.ids):
                raise UserError(
                    self.env._(
                        "AI agents can not receive direct messages: start a "
                        "conversation with the agent instead."
                    )
                )
        return super().channel_get(partners_to, pin=pin, force_open=force_open)

    def _channel_basic_info(self):
        data = super()._channel_basic_info()
        if self.channel_type == "ai_agent":
            data["ai_agent_id"] = self.ai_agent_id.id
            data["ai_res_model"] = self.ai_res_model or False
            data["ai_res_id"] = self.ai_res_id or False
            data["ai_res_display_name"] = self.ai_res_display_name or False
            data["ai_context"] = self.ai_context or False
        return data
