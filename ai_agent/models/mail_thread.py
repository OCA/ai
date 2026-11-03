# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    def message_post(self, **kwargs):
        message = super().message_post(**kwargs)
        self._ai_agent_maybe_trigger(message)
        return message

    def _ai_agent_maybe_trigger(self, message):
        self.ensure_one()
        if message.message_type != "comment" or not message.body:
            return
        agent = self._ai_agent_resolve(message)
        if not agent:
            return
        if message.author_id == agent.user_id.partner_id:
            # The agent's own reply re-entering message_post: stop here,
            # never re-trigger on it.
            return
        human = message.author_id.user_ids[:1]
        if not human:
            return
        session = self.env["ai.agent.session"]._get_or_create_session(
            agent, human, self._name, self.id, message=message
        )
        # Never call the AI here: this is the request of the user. The worker
        # cron answers once this transaction (and the message) is committed.
        session._enqueue_turn(message)

    def _ai_agent_resolve(self, message):
        """Find the ai.agent this message is addressed to, if any.

        - On an AI agent conversation (discuss.channel, channel_type
          'ai_agent'): the agent of the conversation, no mention needed.
        - On any other mail.thread record: the agent must be explicitly
          mentioned (present in the message's partner_ids).
        Resolved without leaking sudo() onto the returned recordset, so
        callers keep executing as the current (writer's) user.
        """
        self.ensure_one()
        agent = self.env["ai.agent"]
        if self._name == "discuss.channel" and self.channel_type == "ai_agent":
            # sudo: ai.agent - the channel is readable, so is its agent id
            agent_id = self.sudo().ai_agent_id.active and self.sudo().ai_agent_id.id
        elif message.partner_ids:
            agent_id = (
                self.env["ai.agent"]
                .sudo()
                .search(
                    [("user_id.partner_id", "in", message.partner_ids.ids)],
                    limit=1,
                )
                .id
            )
        else:
            return agent
        return agent.browse(agent_id) if agent_id else agent
