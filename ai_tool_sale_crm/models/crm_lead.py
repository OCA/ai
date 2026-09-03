# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import models

from odoo.addons.ai_tool.tools import aitool


class CrmLead(models.Model):
    _inherit = "crm.lead"

    @aitool(
        input_schema={
            "lead_id": {
                "type": "integer",
                "description": "ID of the Lead / Opportunity",
            },
            "stage_id": {
                "type": "integer",
                "description": "ID of the target CRM Stage",
            },
        },
        required_inputs=["lead_id", "stage_id"],
        output_schema={
            "success": {"type": "boolean"},
            "stage_name": {"type": "string"},
        },
    )
    def _ai_update_lead_stage(self, lead_id, stage_id, **kwargs):
        lead = self.env["crm.lead"].browse(lead_id)
        if not lead.exists():
            raise ValueError(f"Lead ID {lead_id} does not exist.")
        stage = self.env["crm.stage"].browse(stage_id)
        if not stage.exists():
            raise ValueError(f"Stage ID {stage_id} does not exist.")
        lead.write({"stage_id": stage.id})
        return {"success": True, "stage_name": stage.name}
