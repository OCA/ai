# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.osv import expression
from odoo.tools.mail import plaintext2html

from odoo.addons.mail.tools.discuss import Store

SIDEBAR_SESSIONS_LIMIT = 5


class AiAgent(models.Model):
    _name = "ai.agent"
    _description = "AI Agent"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    user_id = fields.Many2one(
        "res.users",
        string="Agent User",
        required=True,
        help="The user that identifies this agent. Its replies are posted "
        "as mail.message authored by this user.",
    )
    connection_id = fields.Many2one(
        "ai.connection",
        string="Default Connection",
        required=True,
    )
    system_prompt = fields.Text()
    tool_ids = fields.Many2many(
        "ai.tool",
        string="Tools",
    )
    skill_ids = fields.Many2many(
        "ai.skill",
        string="Skills",
    )

    def _ai_get_system_prompt(self):
        self.ensure_one()
        prompt_parts = []
        if self.system_prompt:
            prompt_parts.append(self.system_prompt)
        if self.skill_ids:
            skills_text = []
            for skill in self.skill_ids:
                skills_text.append(f"### Skill: {skill.name}\n\n{skill.content}")
            prompt_parts.append(
                "--- PRELOADED SKILLS ---\n\n" + "\n\n".join(skills_text)
            )
        return "\n\n".join(prompt_parts)

    _sql_constraints = [
        (
            "user_id_unique",
            "unique(user_id)",
            "A user can only be linked to one AI agent.",
        ),
    ]

    @api.model
    def _ai_get_agent_partners(self):
        """Partners of every active agent, whatever the rights of the user."""
        # sudo: ai.agent - only the partners are returned
        return self.sudo().search([]).user_id.partner_id

    # ------------------------------------------------------------
    # Discuss
    # ------------------------------------------------------------

    def action_start_conversation(
        self,
        body,
        res_model=None,
        res_id=None,
        in_chat_window=False,
        view_context=None,
    ):
        """Start a new conversation of the current user with this agent.

        Creates the ``ai_agent`` channel and posts ``body`` on it as the
        first message of the user, which enqueues the first turn. Returns
        the store data of the channel and its id. ``in_chat_window`` keeps
        the conversation open in the chat windows of the user.

        The context of the conversation is a document (``res_model`` and
        ``res_id``) and/or the view the user was looking at
        (``view_context``, see ``_ai_clean_view_context``).
        """
        self.ensure_one()
        body = (body or "").strip()
        if not body:
            raise UserError(self.env._("The message can not be empty."))
        values = {
            "name": self.env["ai.agent.session"]._ai_provisional_title(body),
            "channel_type": "ai_agent",
            "ai_agent_id": self.id,
            "channel_member_ids": [
                Command.create({"partner_id": self.user_id.partner_id.id}),
                Command.create(
                    {
                        "partner_id": self.env.user.partner_id.id,
                        "fold_state": "open" if in_chat_window else "closed",
                    }
                ),
            ],
        }
        if res_model and res_id:
            document = self.env[res_model].browse(int(res_id)).exists()
            document.check_access("read")
            values.update(ai_res_model=document._name, ai_res_id=document.id)
        elif res_model and res_model in self.env:
            self.env[res_model].check_access("read")
            values["ai_res_model"] = res_model
        if values.get("ai_res_model") and view_context:
            values["ai_context"] = self._ai_clean_view_context(view_context)
        channel = self.env["discuss.channel"].create(values)
        channel.message_post(
            body=Markup(plaintext2html(body)),
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        return {
            "channel_id": channel.id,
            "data": Store(channel).get_result(),
        }

    @api.model
    def _ai_clean_view_context(self, view_context):
        """Keep only the expected keys and types of a view context."""

        def strings(values):
            return [str(v) for v in values or [] if isinstance(v, str | int | float)]

        context = {
            "action_name": str(view_context.get("action_name") or "")[:256],
            "view_type": str(view_context.get("view_type") or "")[:32],
            "group_by": strings(view_context.get("group_by"))[:10],
            "facets": strings(view_context.get("facets"))[:20],
        }
        domain = view_context.get("domain")
        if isinstance(domain, list):
            context["domain"] = domain
        return {key: value for key, value in context.items() if value}

    @api.model
    def get_sidebar_data(self, limit=SIDEBAR_SESSIONS_LIMIT):
        """Agents of the Discuss sidebar with the last sessions of the user."""
        Session = self.env["ai.agent.session"]
        result = []
        for agent in self.search([]):
            sessions = Session.search(
                [("agent_id", "=", agent.id), ("user_id", "=", self.env.uid)],
                order="last_activity desc, id desc",
                limit=limit,
            )
            result.append(
                dict(agent._ai_sidebar_info(), sessions=sessions._ai_sidebar_info())
            )
        return result

    @api.model
    def search_sessions(self, agent_id, term="", offset=0, limit=20):
        """Every session of the current user with an agent, for the history."""
        domain = [("agent_id", "=", agent_id), ("user_id", "=", self.env.uid)]
        if term:
            domain = expression.AND(
                [
                    domain,
                    expression.OR(
                        [
                            [("name", "ilike", term)],
                            [("first_message", "ilike", term)],
                            [("res_name", "ilike", term)],
                        ]
                    ),
                ]
            )
        Session = self.env["ai.agent.session"]
        sessions = Session.search(
            domain, order="last_activity desc, id desc", offset=offset, limit=limit
        )
        return {
            "count": Session.search_count(domain),
            "sessions": sessions._ai_sidebar_info(),
        }

    def _ai_sidebar_info(self):
        self.ensure_one()
        return {
            "id": self.id,
            "name": self.name,
            "user_id": self.user_id.id,
            "partner_id": self.user_id.partner_id.id,
        }
