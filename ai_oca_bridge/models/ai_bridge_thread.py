# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class AiBridgeThread(models.AbstractModel):
    _name = "ai.bridge.thread"
    _description = "AI Bridge Mixin"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        model_id = self.sudo().env["ir.model"]._get_id(self._name)
        for bridge in self.env["ai.bridge"].search(
            [("model_id", "=", model_id), ("usage", "=", "ai_thread_create")]
        ):
            for record in records:
                if bridge._enabled_for(record):
                    try:
                        bridge.execute_ai_bridge(record._name, record.id)
                    except Exception as e:
                        _logger.error(
                            "Error creating AI thread for creation on %s: %s",
                            record,
                            e,
                        )
        return records

    def write(self, values):
        result = super().write(values)
        model_id = self.sudo().env["ir.model"]._get_id(self._name)
        for bridge in self.env["ai.bridge"].search(
            [("model_id", "=", model_id), ("usage", "=", "ai_thread_write")]
        ):
            for record in self:
                if bridge._enabled_for(record):
                    try:
                        bridge.execute_ai_bridge(record._name, record.id)
                    except Exception as e:
                        _logger.error(
                            "Error writing AI thread for writing on %s: %s",
                            record,
                            e,
                        )
        return result

    def unlink(self):
        model_id = self.sudo().env["ir.model"]._get_id(self._name)
        executions = self.env["ai.bridge.execution"]
        for bridge in self.env["ai.bridge"].search(
            [("model_id", "=", model_id), ("usage", "=", "ai_thread_unlink")]
        ):
            for record in self:
                if bridge._enabled_for(record):
                    executions |= self.env["ai.bridge.execution"].create(
                        {
                            "ai_bridge_id": bridge.id,
                            "model_id": model_id,
                            "res_id": record.id,
                        }
                    )
        result = super().unlink()
        for execution in executions:
            try:
                execution._execute()
            except Exception as e:
                _logger.error(
                    "Error executing AI thread unlink for %s: %s",
                    self,
                    e,
                )
        return result
