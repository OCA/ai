# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import models

from odoo.addons.ai_tool.tools import aitool


class CrmLead(models.Model):
    _inherit = "crm.lead"

    def _resolve_crm_stage(self, stage_id=None, stage_name=None):
        if isinstance(stage_id, int) and stage_id > 0:
            stage = self.env["crm.stage"].browse(stage_id)
            if stage.exists():
                return stage
        search_name = stage_name or (stage_id if isinstance(stage_id, str) else None)
        if search_name:
            stage = self.env["crm.stage"].search(
                [("name", "ilike", search_name.strip())], limit=1
            )
            if not stage:
                stage = (
                    self.env["crm.stage"]
                    .with_context(lang="en_US")
                    .search([("name", "ilike", search_name.strip())], limit=1)
                )
            if stage:
                return stage
        raise ValueError(
            f"Stage (stage_id={stage_id!r}, stage_name={stage_name!r}) does not exist."
        )

    @aitool(
        input_schema={
            "lead_id": {
                "type": "integer",
                "description": "ID of the Lead / Opportunity",
            },
            "stage_id": {
                "type": "integer",
                "description": (
                    "ID of the target CRM Stage (optional if stage_name is provided)"
                ),
            },
            "stage_name": {
                "type": "string",
                "description": (
                    "Name of the target CRM Stage (e.g. 'Qualified', 'Proposition')"
                ),
            },
        },
        required_inputs=[],
        output_schema={
            "success": {"type": "boolean"},
            "stage_name": {"type": "string"},
        },
    )
    def _ai_update_lead_stage(
        self,
        lead_id=None,
        stage_id=None,
        stage_name=None,
        record=None,
        **kwargs,
    ):
        target_lead_id = lead_id or (
            record.id if record is not None and record._name == "crm.lead" else None
        )
        lead = self.env["crm.lead"].browse(target_lead_id or 0)
        if not lead.exists():
            raise ValueError(f"Lead ID {target_lead_id} does not exist.")
        stage = self._resolve_crm_stage(stage_id=stage_id, stage_name=stage_name)
        lead.write({"stage_id": stage.id})
        return {"success": True, "stage_name": stage.name}
