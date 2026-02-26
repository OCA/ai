# Copyright 2026 Trobz
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.tools.safe_eval import safe_eval


class AiBridge(models.Model):

    _inherit = "ai.bridge"

    is_scheduled = fields.Boolean(
        string="Enable Scheduler",
        default=False,
        help="If enabled, this bridge runs automatically on a schedule "
        "against all records matching the configured domain.",
    )
    cron_id = fields.Many2one(
        "ir.cron",
        readonly=True,
        copy=False,
        ondelete="set null",
    )
    schedule_interval_number = fields.Integer(default=1)
    schedule_interval_type = fields.Selection(
        [
            ("minutes", "Minutes"),
            ("hours", "Hours"),
            ("days", "Days"),
            ("weeks", "Weeks"),
            ("months", "Months"),
        ],
        default="weeks",
    )
    schedule_nextcall = fields.Datetime(
        related="cron_id.nextcall",
        string="Next Execution Date",
        readonly=False,
    )

    def _get_model_fields(self):
        res = super()._get_model_fields()
        if self.is_scheduled:
            res["model_required"] = True
        return res

    def _get_cron_vals(self):
        self.ensure_one()
        return {
            "name": _("AI Bridge: %s") % self.name,
            "model_id": self.env["ir.model"]._get_id("ai.bridge"),
            "state": "code",
            "code": "model.browse(%s)._run_schedule()" % self.id,
            "active": self.active,
            "interval_number": self.schedule_interval_number or 1,
            "interval_type": self.schedule_interval_type or "weeks",
            "numbercall": -1,
            "doall": False,
        }

    def _sync_cron(self):
        for bridge in self:
            if bridge.is_scheduled and bridge.active:
                cron_vals = bridge._get_cron_vals()
                if bridge.cron_id:
                    bridge.cron_id.sudo().write(cron_vals)
                else:
                    cron = self.env["ir.cron"].sudo().create(cron_vals)
                    # Use SQL to avoid recursion through write override
                    self.env.cr.execute(
                        "UPDATE ai_bridge SET cron_id = %s WHERE id = %s",
                        (cron.id, bridge.id),
                    )
                    bridge.invalidate_cache(
                        ["cron_id", "schedule_nextcall"],
                        [bridge.id],
                    )
            else:
                if bridge.cron_id:
                    bridge.cron_id.sudo().unlink()
                    self.env.cr.execute(
                        "UPDATE ai_bridge SET cron_id = NULL WHERE id = %s",
                        (bridge.id,),
                    )
                    bridge.invalidate_cache(
                        ["cron_id", "schedule_nextcall"],
                        [bridge.id],
                    )

    def _run_schedule(self):
        self.ensure_one()
        if not self.is_scheduled or not self.active or not self.model_id:
            return
        domain = safe_eval(self.domain or "[]")
        records = self.env[self.model_id.model].search(domain)
        for record in records:
            self.execute_ai_bridge(record._name, record.id)

    @api.model_create_multi
    def create(self, vals_list):
        nextcalls = [vals.pop("schedule_nextcall", None) for vals in vals_list]
        records = super().create(vals_list)
        records.filtered("is_scheduled")._sync_cron()
        for record, nextcall in zip(records, nextcalls):
            if nextcall and record.cron_id:
                record.cron_id.sudo().write({"nextcall": nextcall})
        return records

    def write(self, vals):
        result = super().write(vals)
        schedule_fields = {
            "is_scheduled",
            "active",
            "name",
            "schedule_interval_number",
            "schedule_interval_type",
            "model_id",
        }
        if schedule_fields & set(vals.keys()):
            for bridge in self:
                if bridge.is_scheduled or "is_scheduled" in vals:
                    bridge._sync_cron()
        return result

    def unlink(self):
        crons = self.mapped("cron_id")
        result = super().unlink()
        crons.sudo().unlink()
        return result
