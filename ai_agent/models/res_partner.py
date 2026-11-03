# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models
from odoo.osv import expression


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.readonly
    @api.model
    def im_search(self, name, limit=20, excluded_ids=None):
        # AI agents are talked to through their own conversations, never
        # through direct messages
        excluded_ids = list(excluded_ids or [])
        excluded_ids += self.env["ai.agent"]._ai_get_agent_partners().ids
        return super().im_search(name, limit=limit, excluded_ids=excluded_ids)

    @api.readonly
    @api.model
    def search_for_channel_invite(self, search_term, channel_id=None, limit=30):
        return super(
            ResPartner, self.with_context(ai_agent_exclude_agents=True)
        ).search_for_channel_invite(search_term, channel_id=channel_id, limit=limit)

    @api.model
    def _search(self, domain, *args, **kwargs):
        if self.env.context.get("ai_agent_exclude_agents"):
            agent_partners = self.env["ai.agent"]._ai_get_agent_partners()
            domain = expression.AND([domain, [("id", "not in", agent_partners.ids)]])
        return super()._search(domain, *args, **kwargs)
