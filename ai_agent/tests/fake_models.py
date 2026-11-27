# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models

from odoo.addons.ai_connection.tests.fake_models import AiConnection  # noqa: F401
from odoo.addons.ai_tool.tools import aitool


class AiAgentTestTool(models.Model):
    _name = "ai.agent.test.tool"
    _description = "AI Agent Test Tool"

    @aitool(
        input_schema={},
        output_schema={"uid": {"type": "integer"}},
    )
    def _ai_get_uid(self):
        return {"uid": self.env.uid}

    @aitool(
        input_schema={},
        output_schema={"count": {"type": "integer"}},
    )
    def _ai_count_params(self):
        # ir.config_parameter is restricted to base.group_system
        return {"count": self.env["ir.config_parameter"].search_count([])}


class AiAgentTestDocument(models.Model):
    """A generic mail.thread document, standing in for "any business
    record" a human could @mention an agent on. Deliberately not
    res.partner: stock base.group_user only has *read* access to
    res.partner (group_partner_manager is needed to write/message_post on
    it), which would make these tests depend on an unrelated ACL quirk
    instead of the ai_agent mention-trigger logic being tested.
    """

    _name = "ai.agent.test.document"
    _description = "AI Agent Test Document"
    _inherit = ["mail.thread"]

    name = fields.Char()
