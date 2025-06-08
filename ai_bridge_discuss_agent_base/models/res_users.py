from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    is_ai_agent = fields.Boolean("Is AI Agent")
    agent_category_id = fields.Many2one("agent.category", string="Agent Category")
    api_type = fields.Selection(
        [("custom_api", "Custom API")],
        string="API Type",
        default="custom_api",
        required=True,
        help="Specify the type of API the agent uses.",
    )
    api_configuration_id = fields.Many2one(
        "agent.api.configuration",
        string="Agent API Configuration",
        help="Configuration for the agent API.",
    )
    api_endpoint = fields.Char(
        "Agent endpoint", help="http://www.example.com/endpoints/agent"
    )
    api_timeout = fields.Integer(
        help="Timeout in seconds for the agent to respond",
        default=30,
    )
    simulated_delay = fields.Boolean(
        "Simulated Delay?",
        help="Simulate a delay in the response of the agent",
    )
    simulated_delay_min = fields.Integer(
        "Simulated Delay Min (seconds)",
        help="Minimum simulated delay in seconds for the agent response",
        default=1,
    )
    simulated_delay_max = fields.Integer(
        "Simulated Delay Max (seconds)",
        help="Maximum simulated delay in seconds for the agent response",
        default=3,
    )
    auth_type = fields.Selection(
        [
            ("none", "None"),
            ("token", "Header Token"),
        ],
        string="Authentication Type",
        help="Authentication type for the agent endpoint",
        default="none",
        required=True,
    )
    header_auth_token = fields.Char(
        "Header Token",
        help="Header token for the agent endpoint",
        default="",
    )
    interaction_ids = fields.Many2many(
        "mail.message",
        string="Interactions",
        help="AI agent Interactions",
        compute="_compute_interaction_ids",
        readonly=True,
    )
    interactions_count = fields.Integer(
        compute="_compute_interactions_count",
    )

    api_parameter_ids = fields.Many2many(
        comodel_name="agent.api.parameter",
        string="API Parameters",
    )

    custom_api_response_key = fields.Char(
        help="Name of the response string from the agent API. Used for custom API type",
        string="Response Key",
    )
    custom_api_method = fields.Selection(
        [("get", "GET"), ("post", "POST")],
        string="API Method",
        default="post",
        required=True,
        help="HTTP method to use for the API call.",
    )

    @api.model
    def _keep_user_online(self):
        agents_list = self.get_agent_users()
        inactivity_period = 100  # 100 milliseconds

        for user in agents_list:
            presence = self.env["bus.presence"].search(
                [("user_id", "=", user.id)], limit=1
            )

            if presence:
                presence.sudo().update_presence(
                    inactivity_period=inactivity_period,
                    identity_field="user_id",
                    identity_value=user.id,
                )
            else:
                new_presence = (
                    self.env["bus.presence"]
                    .sudo()
                    .create(
                        {
                            "user_id": user.id,
                            "last_poll": fields.Datetime.now(),
                        }
                    )
                )
                new_presence.sudo().update_presence(
                    inactivity_period=inactivity_period,
                    identity_field="user_id",
                    identity_value=user.id,
                )

    def get_agent_users(self):
        return self.env["res.users"].search([("is_ai_agent", "=", True)])

    def get_human_users(self):
        return self.env["res.users"].search([("is_ai_agent", "=", False)])

    def _compute_interaction_ids(self):
        for user in self:
            if user.partner_id:
                user.interaction_ids = self.env["mail.message"].search(
                    [
                        ("author_id", "=", user.partner_id.id),
                        ("is_ai_agent_failed", "=", False),
                    ]
                )
            else:
                user.interaction_ids = self.env["mail.message"]

    def _compute_interactions_count(self):
        for user in self:
            user.interactions_count = len(user.interaction_ids)

    def get_api_parameters_for_partner(self, partner=None):
        self.ensure_one()
        result = {}
        for param in self.api_parameter_ids:
            result[param.name] = param.evaluate_for_partner(partner)
        return result

    def action_open_interactions(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Interactions",
            "view_mode": "tree,form",
            "res_model": "mail.message",
            "domain": [("id", "in", self.interaction_ids.ids)],
            "context": {"default_author_id": self.partner_id.id},
        }


class AgentCategory(models.Model):
    _name = "agent.category"

    _description = "AI Agent Category"

    name = fields.Char(required=True)
    description = fields.Text(translate=True)
