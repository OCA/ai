# Copyright 2026 SDi
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class AiConnectionRunWizard(models.TransientModel):
    _name = "ai.connection.run.wizard"
    _description = "Wizard to test AI Connection"

    connection_id = fields.Many2one("ai.connection", required=True)
    prompt = fields.Text(required=True)
    system_prompt = fields.Text()
    tool_ids = fields.Many2many("ai.tool", string="Tools")

    store = fields.Boolean(string="Store Execution", default=True)
    stepwise = fields.Boolean(string="Step-by-Step Mode")
    debug = fields.Boolean(string="Debug Mode")
    stream = fields.Boolean(string="Stream Mode")
    stream_batch_size = fields.Integer(default=40)
    max_iterations = fields.Integer(default=50)

    response_content = fields.Text(string="Response", readonly=True)

    def action_run(self):
        self.ensure_one()
        res = self.connection_id._run(
            prompt=self.prompt,
            system_prompt=self.system_prompt,
            tools=self.tool_ids,
            store=self.store,
            stepwise=self.stepwise,
            debug=self.debug,
            stream=self.stream,
            stream_batch_size=self.stream_batch_size,
            max_iterations=self.max_iterations,
        )
        if self.store:
            return {
                "type": "ir.actions.act_window",
                "res_model": "ai.connection.execution",
                "res_id": res.id,
                "view_mode": "form",
                "target": "current",
            }
        else:
            self.response_content = res[0]
            return {
                "type": "ir.actions.act_window",
                "res_model": "ai.connection.run.wizard",
                "res_id": self.id,
                "view_mode": "form",
                "target": "new",
            }
