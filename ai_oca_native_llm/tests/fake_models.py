from odoo import models


class FakeModel(models.AbstractModel):
    _name = "fake.model"
    _inherit = "ai.llm.client"
    _description = "Fake Model for AI LLM Client testing"
