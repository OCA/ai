# Copyright 2026 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, models


class AiThread(models.Model):
    _inherit = "ai.thread"

    @api.model
    def get_user_active_threads(self, limit=10):
        """Return active and recent AI threads for current user for
        the Systray widget."""
        threads = self.search(
            [("user_id", "=", self.env.user.id)],
            order="create_date desc",
            limit=limit,
        )
        res = []
        for th in threads:
            last_msg = th.message_ids.sorted("create_date")[-1:]
            last_status = last_msg.status if last_msg else "done"
            last_content = last_msg.content if last_msg else ""

            record_name = th.name
            target_record = th.record
            if target_record:
                record_name = getattr(target_record, "display_name", None) or th.name

            res.append(
                {
                    "id": th.id,
                    "name": th.name,
                    "res_model": th.res_model,
                    "res_id": th.res_id,
                    "record_name": record_name,
                    "status": last_status,
                    "pending_jobs": th.pending_job_count,
                    "last_content": last_content,
                    "create_date": th.create_date.strftime("%Y-%m-%d %H:%M:%S")
                    if th.create_date
                    else "",
                }
            )
        return res
