from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def get_ai_agent_partners(self):
        agent_users = self.env["res.users"].get_agent_users()
        return self.env["res.partner"].search([("user_ids", "in", agent_users.ids)])

    def get_human_partners(self):
        agent_users = self.env["res.users"].get_human_users()
        return self.env["res.partner"].search([("user_ids", "in", agent_users.ids)])
