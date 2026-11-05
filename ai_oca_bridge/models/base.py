# Copyright 2025 Dixmit
# Copyright 2025 Binhex - Ariel Barreiros
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class Base(models.AbstractModel):
    _inherit = "base"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._execute_ai_bridges_for_records(records, "ai_thread_create")
        return records

    def write(self, values):
        result = super().write(values)
        self._execute_ai_bridges_for_records(self, "ai_thread_write")
        return result

    def unlink(self):
        executions = self.env["ai.bridge.execution"]
        executions = self._prepare_execution_ai_bridges_unlink(self)
        result = super().unlink()

        for execution in executions:
            try:
                execution._execute()
            except Exception as e:
                _logger.error(
                    f"Error executing AI bridge {execution.ai_bridge_id.name} "
                    f"for unlink on record ID {execution.res_id}: {e}"
                )

        return result

    def _execute_ai_bridges_for_records(self, records, usage):
        if not records:
            return
        model_id = self.sudo().env["ir.model"]._get_id(records._name)
        bridges = (
            self.env["ai.bridge"]
            .sudo()
            .search([("model_id", "=", model_id), ("usage", "=", usage)])
        )
        for bridge in bridges:
            for record in records:
                if bridge._enabled_for(record):
                    try:
                        bridge.execute_ai_bridge(record._name, record.id)
                    except Exception as e:
                        _logger.error(
                            f"Error executing AI bridge {bridge.name} "
                            f"for {usage} on {record}: {e}"
                        )

    def _prepare_execution_ai_bridges_unlink(self, records):
        if not records:
            return self.env["ai.bridge.execution"]

        model_id = self.env["ir.model"]._get_id(records._name)
        bridges = self.env["ai.bridge"].search(
            [("model_id", "=", model_id), ("usage", "=", "ai_thread_unlink")]
        )

        executions = self.env["ai.bridge.execution"]
        for bridge in bridges:
            for record in records:
                if bridge._enabled_for(record):
                    executions |= self.env["ai.bridge.execution"].create(
                        {
                            "ai_bridge_id": bridge.id,
                            "model_id": model_id,
                            "res_id": record.id,
                        }
                    )

        return executions
