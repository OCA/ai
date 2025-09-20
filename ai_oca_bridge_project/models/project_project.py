from odoo import models


class ProjectProject(models.Model):
    _inherit = ["project.project", "ai.bridge.thread"]
    _name = "project.project"
