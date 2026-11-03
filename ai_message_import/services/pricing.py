# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Discount arithmetic and currency conversion of the quoted amounts."""

from odoo import fields


def combine_discounts(line_discount, global_discount):
    """Percent equivalent to a line discount followed by a global discount."""
    remaining = (1 - (line_discount or 0.0) / 100) * (
        1 - (global_discount or 0.0) / 100
    )
    return (1 - remaining) * 100


def quoted_net_amount(line):
    """Amount of a quoted line after its own discount, ``None`` without price."""
    if line.get("price_unit") is None or not line.get("quantity"):
        return None
    return (
        line["quantity"]
        * line["price_unit"]
        * (1 - (line.get("discount_percent") or 0.0) / 100)
    )


def global_discount_rate(discount, lines, tolerance=0.05):
    """Rate of the global discount of a quote, measured on the quoted amounts.

    The rate is measured on every quoted line, valid or not, so the share of a
    line left for review is not loaded on the others.

    :return: ``(rate, base, error)``; ``rate`` is ``None`` when there is no
        global discount or when it cannot be applied safely, ``error`` is then
        ``"mismatch"``, ``"no_base"`` or ``"too_large"``.
    """
    percent, amount = discount.get("percent"), discount.get("amount")
    if not percent and not amount:
        return None, None, None
    amounts = [quoted_net_amount(line) for line in lines]
    base = None if None in amounts else sum(amounts)
    if percent and amount:
        if base is not None and abs(base * percent / 100 - amount) > tolerance:
            return None, base, "mismatch"
        return percent, base, None
    if percent:
        return percent, base, None
    if not base or base <= 0:
        return None, base, "no_base"
    rate = amount / base * 100
    if rate >= 100:
        return None, base, "too_large"
    return rate, base, None


class CurrencyConverter:
    """Convert quoted amounts to the currency of the company.

    Only the rates recorded in Odoo are used: when the currency or its rates are
    missing, ``error`` is set and ``convert`` returns ``None``.
    """

    def __init__(self, env, company, currency_code, date=None):
        self.env = env
        self.company = company
        self.company_currency = company.currency_id
        self.date = date or fields.Date.context_today(env.user)
        self.code = currency_code or self.company_currency.name
        self.currency = self.company_currency
        self.rate = 1.0
        self.rate_date = None
        self.error = None
        if self.code != self.company_currency.name:
            self._load_rate()

    @property
    def is_foreign(self):
        return self.currency != self.company_currency

    def _load_rate(self):
        currency = (
            self.env["res.currency"]
            .with_context(active_test=False)
            .search([("name", "=", self.code)], limit=1)
        )
        if not currency:
            self.currency = None
            self.error = self.env._(
                "The currency %(code)s does not exist in Odoo.", code=self.code
            )
            return
        self.currency = currency
        Rate = self.env["res.currency.rate"].sudo()
        domain = [
            ("currency_id", "=", currency.id),
            ("company_id", "in", [False, self.company.id, self.company.root_id.id]),
        ]
        rate = Rate.search(
            domain + [("name", "<=", self.date)], order="name desc", limit=1
        ) or Rate.search(domain, order="name asc", limit=1)
        if not rate:
            self.error = self.env._(
                "Odoo has no exchange rate for %(code)s.", code=self.code
            )
            return
        self.rate_date = rate.name
        self.rate = currency._get_conversion_rate(
            currency, self.company_currency, self.company, self.date
        )

    def convert(self, amount):
        if amount is None or self.error:
            return None
        if not self.is_foreign:
            return amount
        return self.currency._convert(
            amount, self.company_currency, self.company, self.date, round=False
        )

    def describe(self):
        if not self.is_foreign:
            return ""
        if self.error:
            return self.error
        return self.env._(
            "1 %(code)s = %(rate).6f %(company_currency)s (Odoo rate of "
            "%(rate_date)s, applied on %(date)s)",
            code=self.code,
            rate=self.rate,
            company_currency=self.company_currency.name,
            rate_date=self.rate_date,
            date=self.date,
        )
