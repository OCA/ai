from odoo import models


class ProjectTask(models.Model):
    _inherit = ["project.task", "ai.bridge.thread"]
    _name = "project.task"
