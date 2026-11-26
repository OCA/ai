# Copyright 2026 Nimarosa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import datetime

import pytz
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

#: System parameter: the timezone the day (and so the month) of a call is
#: counted in. UTC when unset or invalid.
TZ_PARAM = "ai_connection_usage.timezone"


class AiConnectionUsage(models.Model):
    _name = "ai.connection.usage"
    _description = "AI Connection Usage"
    _order = "id desc"
    _rec_name = "connection_id"

    connection_id = fields.Many2one(
        "ai.connection", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one("res.company", required=True, index=True)
    user_id = fields.Many2one("res.users", required=True, index=True)
    date = fields.Date(
        required=True,
        index=True,
        default=lambda self: self._usage_today(),
        help="Day of the call in the timezone of the system parameter "
        "ai_connection_usage.timezone (UTC by default): the monthly caps count "
        "calendar months of that timezone.",
    )
    purpose = fields.Char(help="What the call was made for, set by the caller.")
    res_model = fields.Char(string="Related Model", index=True)
    res_id = fields.Many2oneReference(string="Related Record", model_field="res_model")
    model_name = fields.Char(string="AI Model")
    state = fields.Selection(
        [("done", "Done"), ("error", "Error")], required=True, default="done"
    )
    error = fields.Text()
    prompt_tokens = fields.Integer()
    completion_tokens = fields.Integer()
    iterations = fields.Integer()
    duration = fields.Float(help="Duration of the call, in seconds.")
    currency_id = fields.Many2one("res.currency")
    cost = fields.Float(
        digits=(16, 6), help="Cost of the call, in the currency of the connection."
    )
    cost_company = fields.Float(
        string="Cost (Company Currency)",
        digits=(16, 6),
        help="Cost of the call in the currency of the company: the amount the "
        "monthly cap of the company counts.",
    )
    prompt = fields.Text(groups="base.group_system")
    answer = fields.Text(groups="base.group_system")

    @api.model
    def _usage_tz(self):
        name = self.env["ir.config_parameter"].sudo().get_param(TZ_PARAM) or "UTC"
        try:
            return pytz.timezone(name.strip())
        except pytz.UnknownTimeZoneError:
            return pytz.utc

    @api.model
    def _usage_today(self):
        return datetime.datetime.now(self._usage_tz()).date()

    @api.model
    def _month_bounds(self, date):
        start = fields.Date.to_date(date).replace(day=1)
        return start, start + relativedelta(months=1)

    @api.model
    def _month_domain(self, date, company=None, connection=None):
        start, stop = self._month_bounds(date)
        domain = [("date", ">=", start), ("date", "<", stop)]
        if company is not None:
            return domain + [("company_id", "=", company.id)], "cost_company"
        return domain + [("connection_id", "=", connection.id)], "cost"

    @api.model
    def _month_spend(self, date, company=None, connection=None):
        """Spend recorded in this log during the month of ``date``.

        With ``company``: the sum of ``cost_company`` of that company.
        With ``connection``: the sum of ``cost`` of that connection.
        """
        domain, field = self._month_domain(date, company, connection)
        result = self.sudo()._read_group(domain, aggregates=[f"{field}:sum"])
        return result[0][0] or 0.0

    @api.model
    def _month_rows(self, date, company=None, connection=None):
        """``{row id: amount}`` of the month, as this environment sees it."""
        domain, field = self._month_domain(date, company, connection)
        rows = self.sudo().search_read(domain, [field])
        return {row["id"]: row[field] for row in rows}
