# Copyright 2026 Nimarosa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import time

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Positions of ``prompt`` and ``record`` in ``ai.connection._run``
_PROMPT_ARG = 0
_RECORD_ARG = 2


class AiConnection(models.Model):
    _inherit = "ai.connection"

    company_id = fields.Many2one(
        "res.company",
        index=True,
        help="Company whose usage and monthly cap the calls of this connection "
        "count against. Leave it empty to use the current company of the user "
        "and share the connection with every company.",
    )
    usage_currency_id = fields.Many2one(
        "res.currency",
        string="Price Currency",
        default=lambda self: self.env.company.currency_id,
        groups="base.group_system",
    )
    usage_input_price = fields.Float(
        string="Input Price",
        digits=(16, 4),
        groups="base.group_system",
        help="Price of one million prompt tokens.",
    )
    usage_output_price = fields.Float(
        string="Output Price",
        digits=(16, 4),
        groups="base.group_system",
        help="Price of one million completion tokens.",
    )
    usage_month_cap = fields.Float(
        string="Monthly Spending Cap",
        digits=(16, 2),
        groups="base.group_system",
        help="Maximum spend of this connection per calendar month, in the price "
        "currency. Calls are refused once it is reached. Zero means no cap.",
    )
    usage_store_content = fields.Boolean(
        string="Store Prompts and Answers",
        groups="base.group_system",
        help="Keep the prompt and the answer of each call in the usage log. "
        "Off by default: they may contain personal or confidential data.",
    )
    usage_month_spend = fields.Float(
        string="Spend This Month",
        digits=(16, 6),
        compute="_compute_usage_month_spend",
        groups="base.group_system",
    )
    usage_count = fields.Integer(
        compute="_compute_usage_month_spend", groups="base.group_system"
    )

    def _compute_usage_month_spend(self):
        usage = self.env["ai.connection.usage"]
        today = usage._usage_today()
        counts = dict(
            usage.sudo()._read_group(
                [("connection_id", "in", self.ids)], ["connection_id"], ["__count"]
            )
        )
        for connection in self:
            connection.usage_month_spend = usage._month_spend(
                today, connection=connection
            )
            connection.usage_count = counts.get(connection, 0)

    def action_view_usage(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "ai_connection_usage.ai_connection_usage_act_window"
        )
        action["domain"] = [("connection_id", "=", self.id)]
        action["context"] = {"default_connection_id": self.id}
        return action

    def _run(self, *args, **kwargs):
        self.ensure_one()
        company = self._usage_company()
        self._usage_check_cap(company)
        start = time.monotonic()
        try:
            result = super()._run(*args, **kwargs)
        except Exception as error:
            self._usage_log(company, args, kwargs, start, error=error)
            raise
        self._usage_log(company, args, kwargs, start, result=result)
        return result

    def _usage_company(self):
        return self.company_id or self.env.company

    def _usage_check_cap(self, company):
        """Refuse the call before reaching the provider once a cap is spent.

        The spend is read through a cursor of its own, so that the calls this
        same transaction already logged (committed by ``_usage_write``) count.
        """
        connection = self.sudo()
        usage = self.env["ai.connection.usage"]
        today = usage._usage_today()
        if connection.usage_month_cap:
            spend = self._usage_committed_month_spend(today, connection=connection)
            if spend >= connection.usage_month_cap:
                raise UserError(
                    self.env._(
                        "The AI connection %(name)s reached its monthly spending "
                        "cap (%(spend).2f of %(cap).2f %(currency)s). Ask an "
                        "administrator to raise it or wait for next month.",
                        name=connection.name,
                        spend=spend,
                        cap=connection.usage_month_cap,
                        currency=connection.usage_currency_id.name or "",
                    )
                )
        cap = company.sudo().ai_usage_month_cap
        if cap:
            spend = self._usage_committed_month_spend(
                today, company=company
            ) + self._usage_external_month_spend(company, today)
            if spend >= cap:
                raise UserError(
                    self.env._(
                        "The company %(company)s reached its monthly AI spending "
                        "cap (%(spend).2f of %(cap).2f %(currency)s). Ask an "
                        "administrator to raise it or wait for next month.",
                        company=company.name,
                        spend=spend,
                        cap=cap,
                        currency=company.currency_id.name,
                    )
                )

    def _usage_committed_month_spend(self, date, company=None, connection=None):
        """Month spend: every committed row, plus the rows only this
        transaction sees (written in it by the fallback of ``_usage_write``).

        The committed rows are read through a cursor of their own, so the
        calls this same transaction already logged and committed count.
        """
        usage = self.env["ai.connection.usage"]
        here = usage._month_rows(date, company=company, connection=connection)
        try:
            committed = self._usage_committed_rows(date, company, connection)
        except Exception:
            _logger.info("Could not read the committed AI usage", exc_info=True)
            return sum(here.values())
        own = sum(value for key, value in here.items() if key not in committed)
        return sum(committed.values()) + own

    def _usage_committed_rows(self, date, company=None, connection=None):
        with self.env.registry.cursor() as cr:
            env = self.env(cr=cr, su=True)
            return env["ai.connection.usage"]._month_rows(
                date,
                company=company and env["res.company"].browse(company.id),
                connection=connection and env["ai.connection"].browse(connection.id),
            )

    @api.model
    def _usage_external_month_spend(self, company, date):
        """Spend of ``company`` during the month of ``date`` made outside of
        this log, in the company currency.

        Extension point: an integrator whose other features also pay for AI
        calls (outside ``ai.connection``) can add that spend here, so that the
        company monthly cap counts it too.
        """
        return 0.0

    def _usage_cost(self, prompt_tokens, completion_tokens):
        connection = self.sudo()
        return (
            prompt_tokens * connection.usage_input_price
            + completion_tokens * connection.usage_output_price
        ) / 1_000_000

    def _usage_log(self, company, args, kwargs, start, result=None, error=None):
        connection = self.sudo()
        prompt_tokens = completion_tokens = iterations = 0
        answer = None
        if result:
            answer, prompt_tokens, completion_tokens, iterations = result
        record = kwargs.get("record")
        if record is None and len(args) > _RECORD_ARG:
            record = args[_RECORD_ARG]
        cost = self._usage_cost(prompt_tokens or 0, completion_tokens or 0)
        today = self.env["ai.connection.usage"]._usage_today()
        currency = connection.usage_currency_id or company.currency_id
        vals = {
            "connection_id": self.id,
            "company_id": company.id,
            "user_id": self.env.uid,
            "date": today,
            "purpose": self.env.context.get("ai_usage_purpose"),
            "model_name": connection.model,
            "state": "error" if error else "done",
            "error": f"{type(error).__name__}: {error}" if error else False,
            "prompt_tokens": prompt_tokens or 0,
            "completion_tokens": completion_tokens or 0,
            "iterations": iterations or 0,
            "duration": time.monotonic() - start,
            "currency_id": currency.id,
            "cost": cost,
            "cost_company": currency._convert(
                cost, company.currency_id, company, today, round=False
            ),
        }
        if record:
            vals.update(res_model=record._name, res_id=record[:1].id)
        if connection.usage_store_content:
            prompt = kwargs.get("prompt")
            if prompt is None and len(args) > _PROMPT_ARG:
                prompt = args[_PROMPT_ARG]
            vals.update(prompt=prompt, answer=answer)
        self._usage_write(vals)

    def _usage_write(self, vals):
        """Write a usage row in a transaction of its own.

        Committed independently of the caller: the row of a failed call stays
        when the caller rolls back, and the cost of a successful call stays
        (and counts for the caps) even if the caller fails afterwards. When
        that cursor cannot write it (e.g. the connection was created in this
        same, still uncommitted, transaction), the row goes in the caller's
        transaction instead.
        """
        try:
            with self.env.registry.cursor() as cr:
                # never wait long on a lock the caller's transaction may hold
                cr.execute("SET LOCAL lock_timeout = '2s'")
                self.env(cr=cr, su=True)["ai.connection.usage"].create(vals)
            return
        except Exception:
            # Whatever went wrong there, the call itself must not break
            _logger.info(
                "AI usage of connection %s logged in the caller's transaction",
                self.id,
                exc_info=True,
            )
        try:
            with self.env.cr.savepoint():
                self.env["ai.connection.usage"].sudo().create(vals)
        except Exception:
            # Never lose the answer of the provider because the log failed
            _logger.exception("Could not log the usage of AI connection %s", self.id)
