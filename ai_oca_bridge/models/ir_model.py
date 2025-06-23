# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class IrModel(models.Model):

    _inherit = "ir.model"

    is_ai_bridge_thread = fields.Boolean()
    ai_usage = fields.Char(store=False, search="_search_ai_usage")

    def _reflect_model_params(self, model):
        vals = super(IrModel, self)._reflect_model_params(model)
        vals["is_ai_bridge_thread"] = (
            isinstance(model, self.pool["ai.bridge.thread"]) and not model._abstract
        )
        return vals

    def _search_ai_usage(self, operator, value):
        if operator not in ("="):
            return []
        if value == "thread":
            return [("is_mail_thread", "=", True), ("transient", "=", False)]
        if value in ["ai_thread_create", "ai_thread_write", "ai_thread_unlink"]:
            return [("is_ai_bridge_thread", "=", True), ("transient", "=", False)]
        return []
