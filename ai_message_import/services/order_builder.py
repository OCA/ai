# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Turn an interpreted quote into a draft order, or update one.

The AI interprets the documents; the builders validate the result against the
data of Odoo and decide every operation:

* the prices of Odoo prevail over the quoted ones, the quantities come from the
  quote and the units are only converted with the units and packagings of Odoo,
  or with the units inside a box when the prices and the product tell them;
* taxes, fiscal position, payment terms, currency and planning follow the
  standard logic of Odoo, the differences with the quote are documented;
* a line that cannot be processed safely becomes an incident, the others make
  the order;
* the orders stay in draft: they are never confirmed nor cancelled here, and an
  order that is no longer a draft is never modified;
* a value changed by a person after the last automatic update is never
  overwritten, the conflict is recorded instead.

Every decision is written in the internal notes of the order.

``OrderBuilder`` holds the logic common to every document type. Each type
(purchase, sale...) subclasses it with the models, the fields and the rules of
its orders: how its partner is found, the header of its orders, how the prices
of Odoo are computed and how lines and orders are created.
"""

import json
import re
from datetime import date, datetime, time, timedelta

from markupsafe import Markup

from odoo import fields
from odoo.tools import float_compare, float_is_zero, float_round
from odoo.tools.misc import format_date, formatLang

from .ai_client import AIError
from .matching import PartnerMatcher, ProductMatcher, UomResolver, match_payment_term
from .pricing import CurrencyConverter, combine_discounts, global_discount_rate
from .product_chooser import ProductChooser
from .tools import normalize_code, normalize_text, note_author

# The numbers written in the name of a product: one may be the units of its box.
NAME_NUMBER = re.compile(r"(?<![\d.,])\d{1,5}(?![\d.,])")
# Relative difference allowed between the price of a box and the price of the
# units it holds, to tell that a document counts the units of the box.
PACK_PRICE_TOLERANCE = 0.05


class LinePlan:
    """What a quoted line becomes on the order."""

    def __init__(self, qline):
        self.qline = qline
        self.kind = "product"
        self.product = None
        self.uom = None
        self.packaging = None
        self.quantity = 0.0
        self.factor = 1.0
        # Explicit price, only for the products created from the quote.
        self.price_unit = None
        # Quoted price per unit of the order, in the currency of the company.
        self.quoted_price = None
        # Date of the line, for the types whose lines have one.
        self.line_date = None
        self.ok = False
        self.created_product = False

    @property
    def label(self):
        qline = self.qline
        return qline.product_code or qline.description or str(qline.sequence)


class OrderBuilder:
    """Common logic of the builders; see the module documentation."""

    #: Model of the orders and of their lines.
    order_model = None
    line_model = None
    #: Fields of the quotes, quote lines, incidents and changes that link them
    #: to the order and to its lines.
    order_link = None
    line_link = None
    #: Fields of the order lines.
    qty_field = None
    tax_field = None
    #: Field of the lines with their date, ``None`` when the lines have none.
    line_date_field = None
    #: Fields of the order and of its lines kept up to date by the module, used
    #: to detect the changes made by a person.
    order_fields = ()
    line_fields = ()
    #: States of the orders the module may still change.
    editable_states = ("draft", "sent")
    #: Products that can be ordered, and usage of their packagings.
    product_ok_field = None
    packaging_usage = None
    #: Rank of the partners of this type (``supplier_rank``, ``customer_rank``).
    rank_field = None
    #: Also search the references and names of the vendor price lists.
    supplier_steps = False
    #: States of the confirmed orders, which tell the products the partner takes.
    confirmed_states = ()

    def __init__(self, quote):
        self.quote = quote
        self.env = quote.env
        self.company = quote.company_id
        self.sender = quote.sender_id
        self.config = self.env["mail.message.import.config"]._get_for_company(
            self.company
        )
        self.data = quote.extraction or {}
        self.notes = []
        self.incidents = []
        self.changes = []
        self.pending_amount = 0.0
        self.price_difference = 0.0
        self.tax_issue = False
        self.freight_pending = False
        self.discount_pending = False
        self.global_rate = None
        self.global_base = None
        self.delivery_date = None
        self.converter = CurrencyConverter(
            self.env,
            self.company,
            quote.currency_code,
            self._conversion_date(),
        )
        self.uoms = UomResolver(self.env, self.sender)
        self._product_matcher = None
        self.product_matches = {}
        # Products chosen by the AI and candidates of the lines, by quote line.
        self.ai_choices = {}
        self.product_candidates = {}

    # ------------------------------------------------------------------
    # Rules of the document type, given by the subclasses
    # ------------------------------------------------------------------

    def _role(self):
        """Name of the partner in the texts, e.g. ``vendor``, ``customer``."""
        raise NotImplementedError()

    def _order_label(self):
        """Name of the orders in the texts, e.g. ``purchase order``."""
        raise NotImplementedError()

    def _auto_create_partner(self):
        """Whether an unknown partner may be created."""
        return False

    def _partner_min_confidence(self):
        return 1.0

    def _header_values(self, partner):
        """Values of the order stated by the document."""
        raise NotImplementedError()

    def _default_payment_term(self, partner):
        """The payment term Odoo would set on an order of ``partner``."""
        raise NotImplementedError()

    def _order_uom(self, product):
        """Unit of the quantities of ``product`` on the order lines."""
        return product.uom_id

    def _product_creation_blocker(self, qline, uom):
        """Why a product cannot be created from ``qline``, or ``None``."""
        return self.env._("products are not created for this type of document")

    def _create_product(self, qline, uom):
        raise NotImplementedError()

    def _line_date(self, qline):
        """Date of the line, for the types whose lines have one."""
        return False

    def _line_values(self, order, plan):
        """Values to create the line of ``plan``."""
        values = {
            "order_id": order.id,
            "product_id": plan.product.id,
            self.qty_field: plan.quantity,
            "product_uom": plan.uom.id,
            "ai_message_import_document_line_id": plan.qline.id,
            "ai_message_import_line_kind": "product",
            "sequence": 10 + plan.qline.sequence,
        }
        if plan.packaging:
            values["product_packaging_id"] = plan.packaging.id
        return values

    def _recompute_line_prices(self, line):
        """Compute again the prices of Odoo of ``line`` for its quantity."""
        raise NotImplementedError()

    def _change_line_product(self, line, product_id):
        """Set a new product on ``line``, as Odoo does when it is selected."""
        line.write({"product_id": product_id})

    def _odoo_discount(self, line):
        """Discount of ``line`` according to the price lists of Odoo."""
        return 0.0

    def _price_origin(self, line):
        """Where the price of Odoo of ``line`` comes from, for the notes."""
        raise NotImplementedError()

    def _check_zero_price(self, line, plan):
        """Raise an incident when the price of Odoo is suspicious."""

    def _computed_date_note(self, line, plan):
        """Note the date computed by Odoo when the document states none."""

    def _freight_line_values(self, order, product, price):
        raise NotImplementedError()

    def _freight_tax_rate(self, product, order):
        """Tax rate of ``product`` on ``order``, in percent."""
        raise NotImplementedError()

    def _order_values(self, partner, header):
        """Values to create a new order for ``partner``."""
        raise NotImplementedError()

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    def _amount(self, value, currency=None):
        currency = currency or self.company.currency_id
        return formatLang(self.env, value or 0.0, currency_obj=currency)

    def _price(self, value, currency=None):
        """A unit price, with the precision of the prices of Odoo."""
        currency = currency or self.company.currency_id
        return formatLang(
            self.env, value or 0.0, dp="Product Price", currency_obj=currency
        )

    def _quoted_amount(self, value):
        """An amount of the document, in the currency of the document."""
        if self.converter.currency:
            return self._amount(value, self.converter.currency)
        return f"{value or 0.0:.2f} {self.converter.code}"

    def _qty(self, value):
        return formatLang(self.env, value, dp="Product Unit of Measure")

    def _date(self, value):
        return format_date(self.env, value)

    def _conversion_date(self):
        today = fields.Date.context_today(self.quote)
        quote_date = self.quote.quote_date
        return quote_date if quote_date and quote_date <= today else today

    def _quote_order(self, quote=None):
        return (quote or self.quote)[self.order_link]

    def note(self, text):
        self.notes.append(text)

    def incident(self, incident_type, name, description="", qline=None, values=None):
        self.incidents.append(
            {
                "incident_type": incident_type,
                "name": name,
                "description": description,
                "document_line_id": qline.id if qline else False,
                "original_values": json.dumps(
                    values
                    if values is not None
                    else (qline.original_values if qline else {}),
                    indent=2,
                    default=str,
                    ensure_ascii=False,
                ),
            }
        )

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self):
        """Apply the document. :return: the order, or nothing."""
        quote = self.quote
        if quote.relation == "duplicate" and not quote.skip_duplicate_check:
            target = quote.target_quote_id
            evidence = [
                self.env._(
                    "The AI considers it the same document as %(ref)s: %(reason)s",
                    ref=target.name or quote.target_reference or "?",
                    reason=quote.relation_reason or "-",
                )
            ]
            return self._mark_duplicate(target, evidence)
        partner = self._resolve_partner()
        if not partner:
            # The products are proposed anyway, for whoever chooses the partner.
            self._propose_products()
            return self._finish(None, "pending")
        # A quote applied again to its own order is not a new quote.
        if (
            quote.relation != "update"
            and not quote.skip_duplicate_check
            and not self._quote_order()
        ):
            duplicate, evidence = self._find_duplicate(partner)
            if duplicate:
                return self._mark_duplicate(duplicate, evidence)
        # A quote already on an order stays done when one application stops.
        stopped_state = "done" if self._quote_order() else "pending"
        order = self._target_order(partner)
        if order is False:
            return self._finish(None, stopped_state)
        self._check_currency()
        self._check_delivery_date()
        self.global_rate = self._global_discount()
        self._choose_products()
        plans = [self._plan_line(qline) for qline in quote.line_ids]
        valid = [plan for plan in plans if plan.ok]
        if order and not valid:
            # Nothing reliable to apply: the order is left as it is.
            return self._finish(order, stopped_state)
        if not order and not valid:
            self.incident(
                "no_document",
                self.env._("No line of the document can be ordered"),
                self.env._(
                    "The %(order)s was not created because no line could be "
                    "processed safely. Review the incidents of the lines.",
                    order=self._order_label(),
                ),
                values=self.data,
            )
            return self._finish(None, "pending")
        header = self._header_values(partner)
        if order:
            self._update_order(order, header)
        else:
            order = self._create_order(partner, header)
        self._apply_lines(order, plans)
        self._apply_freight(order)
        self._document_discount(order, valid)
        self._check_totals(order)
        return self._finish(order, "done")

    # ------------------------------------------------------------------
    # Partner and duplicates
    # ------------------------------------------------------------------

    def _partner_values(self):
        return self.data.get("partner") or {}

    def _resolve_partner(self):
        quote = self.quote
        if quote.partner_id:
            if quote.partner_match_method in ("manual", "created"):
                return quote.partner_id
            return quote.partner_id.commercial_partner_id
        values = self._partner_values()
        matcher = PartnerMatcher(self.env, self.company, self.sender, self.rank_field)
        match = matcher.match(values)
        if match.record:
            quote.write(
                {"partner_id": match.record.id, "partner_match_method": match.method}
            )
            self.note(
                self.env._(
                    "Partner %(partner)s (%(role)s) identified by %(method)s.",
                    partner=match.record.display_name,
                    role=self._role(),
                    method=dict(
                        quote._fields["partner_match_method"]._description_selection(
                            self.env
                        )
                    ).get(match.method, match.method),
                )
            )
            return match.record
        if match.ambiguous:
            names = match.candidates[:10].mapped("display_name")
            if len(match.candidates) > 10:
                names.append("…")
            reason = self.env._(
                "Several partners match the %(role)s of the document: %(names)s.",
                role=self._role(),
                names=", ".join(names),
            )
        elif match.method == "own" or matcher.is_own_name(values):
            reason = self.env._(
                "The %(role)s of the document looks like the sender or one of the "
                "companies, which can never be the %(role)s.",
                role=self._role(),
            )
        elif self._auto_create_partner() and matcher.can_create(
            values, self._partner_min_confidence()
        ):
            partner, warning = matcher.create_partner(values)
            quote.write({"partner_id": partner.id, "partner_match_method": "created"})
            self.note(
                self.env._(
                    "Partner %(partner)s (%(role)s) created from the document "
                    "(confidence %(conf).0f%%).",
                    partner=partner.display_name,
                    role=self._role(),
                    conf=values.get("confidence", 0.0) * 100,
                )
            )
            if warning:
                self.note(warning)
            return partner
        else:
            reason = self._partner_not_found_reason(matcher, values)
        self.incident(
            "partner",
            self.env._("Partner to be selected (%(role)s)", role=self._role()),
            reason
            + " "
            + self.env._(
                "Select the partner on the document and apply it again: it is "
                "remembered for the next time. The %(order)s is not created "
                "meanwhile.",
                order=self._order_label(),
            ),
            values=values,
        )
        return None

    def _partner_not_found_reason(self, matcher, values):
        """No partner of Odoo is the one of the quote, and it is not created:
        say so, and why it was not created."""
        reason = self.env._(
            "No %(role)s in Odoo matches the one of the document (name: %(name)s, "
            "VAT: %(vat)s).",
            role=self._role(),
            name=values.get("name") or "-",
            vat=values.get("vat") or "-",
        )
        if not self._auto_create_partner():
            why = self.env._(
                "Creating it is disabled in the settings of AI Message Import."
            )
        else:
            min_confidence = self._partner_min_confidence()
            blocker = matcher.create_blocker(values, min_confidence)
            if blocker == "confidence":
                why = self.env._(
                    "It is not created because it was read with too little "
                    "confidence (%(conf).0f%%, minimum %(min).0f%%).",
                    conf=values.get("confidence", 0.0) * 100,
                    min=min_confidence * 100,
                )
            elif blocker == "data":
                why = self.env._(
                    "It is not created because the document gives no VAT number, "
                    "email, phone nor address of it."
                )
            else:
                why = self.env._(
                    "It is not created because the document gives no name of it."
                )
        return f"{reason} {why}"

    def _find_duplicate(self, partner):
        quote = self.quote
        Quote = self.env["ai.message.import.document"]
        # The same file read as another type of document is not a duplicate.
        base = [
            ("sender_id", "=", quote.sender_id.id),
            ("document_type", "=", quote.document_type),
            ("id", "!=", quote.id),
            ("state", "in", ["done", "pending"]),
        ]
        evidence = []
        found = Quote
        checksums = [c for c in quote.attachment_ids.mapped("checksum") if c]
        if checksums:
            # One file may hold several quotes of the same conversation.
            same_file = Quote.search(
                base
                + [
                    ("conversation_id", "!=", quote.conversation_id.id),
                    ("attachment_ids.checksum", "in", checksums),
                ]
            )
            if same_file:
                found |= same_file
                evidence.append(
                    self.env._(
                        "The same file was already received in %(refs)s.",
                        refs=", ".join(same_file.mapped("name")),
                    )
                )
        number_key = normalize_code(quote.quote_number)
        partners = partner.commercial_partner_id
        if number_key:
            same_number = Quote.search(
                base
                + [
                    ("partner_id", "child_of", partners.id),
                    ("quote_number_key", "=", number_key),
                ]
            )
            if same_number:
                found |= same_number
                evidence.append(
                    self.env._(
                        "Document number %(number)s of %(partner)s already received in "
                        "%(refs)s.",
                        number=quote.quote_number,
                        partner=partner.display_name,
                        refs=", ".join(same_number.mapped("name")),
                    )
                )
        total = (self.data.get("totals") or {}).get("total")
        if quote.quote_date and total:
            same_amount = Quote.search(
                base
                + [
                    ("partner_id", "child_of", partners.id),
                    ("quote_date", "=", quote.quote_date),
                ]
            ).filtered(
                lambda q: (
                    float_compare(q.amount_total_doc, total, precision_digits=2) == 0
                )
            )
            if same_amount:
                found |= same_amount
                evidence.append(
                    self.env._(
                        "A document of the same partner, date and total (%(total)s) "
                        "exists: %(refs)s.",
                        total=self._quoted_amount(total),
                        refs=", ".join(same_amount.mapped("name")),
                    )
                )
        return found.sorted("id")[:1], evidence

    def _mark_duplicate(self, original, evidence):
        quote = self.quote
        quote.write(
            {
                "duplicate_of_id": original.id if original else False,
                "duplicate_evidence": "\n".join(evidence),
            }
        )
        self.incident(
            "duplicate",
            self.env._("Possible duplicate of %(ref)s", ref=original.name or "?"),
            "\n".join(evidence)
            + "\n"
            + self.env._(
                "No %(order)s was created. When it is not a duplicate, use 'Not a "
                "duplicate' on the document.",
                order=self._order_label(),
            ),
            values={
                "quote_number": quote.quote_number,
                "quote_date": str(quote.quote_date or ""),
                "totals": self.data.get("totals"),
            },
        )
        return self._finish(
            self._quote_order(original) if original else None, "duplicate"
        )

    # ------------------------------------------------------------------
    # Target order
    # ------------------------------------------------------------------

    def _target_order(self, partner):
        """The order to update, ``None`` for a new one, ``False`` to stop."""
        quote = self.quote
        order = self._quote_order()
        if not order and quote.relation == "update":
            target = quote.target_quote_id
            order = self._quote_order(target)
            if not order:
                self.incident(
                    "update_ambiguous",
                    self.env._(
                        "Correction without an order to update (%(order)s)",
                        order=self._order_label(),
                    ),
                    self.env._(
                        "The AI considers the messages a correction of %(ref)s, but "
                        "no %(order)s can be associated unequivocally. Nothing was "
                        "created: check the document and apply it as a new one if "
                        "needed.",
                        ref=target.name or quote.target_reference or "?",
                        order=self._order_label(),
                    ),
                    values={"reason": quote.relation_reason},
                )
                return False
        if not order:
            return None
        if order.state not in self.editable_states:
            self.incident(
                "order_locked",
                self.env._("%(order)s can no longer be modified", order=order.name),
                self.env._(
                    "The %(label)s %(order)s is %(state)s. Confirmed or cancelled "
                    "orders are never modified automatically: apply the changes of "
                    "the document by hand if they are still relevant.",
                    label=self._order_label(),
                    order=order.name,
                    state=dict(order._fields["state"]._description_selection(self.env))[
                        order.state
                    ],
                ),
                values=self.data,
            )
            return False
        if order.currency_id != self.company.currency_id:
            self.incident(
                "update_ambiguous",
                self.env._(
                    "%(order)s is not in the currency of the company", order=order.name
                ),
                self.env._(
                    "A person changed the currency of %(order)s to %(currency)s. The "
                    "module only writes amounts in %(company_currency)s, so the order "
                    "was not modified.",
                    order=order.name,
                    currency=order.currency_id.name,
                    company_currency=self.company.currency_id.name,
                ),
                values=self.data,
            )
            return False
        if order.partner_id.commercial_partner_id != partner.commercial_partner_id:
            self.incident(
                "update_ambiguous",
                self.env._("The partner differs from %(order)s", order=order.name),
                self.env._(
                    "The correction names the %(role)s %(partner)s while %(order)s "
                    "is for %(order_partner)s. The order was not modified.",
                    role=self._role(),
                    partner=partner.display_name,
                    order=order.name,
                    order_partner=order.partner_id.display_name,
                ),
                values=self._partner_values(),
            )
            return False
        return order

    # ------------------------------------------------------------------
    # Header: currency, dates, payment terms
    # ------------------------------------------------------------------

    def _check_currency(self):
        converter = self.converter
        if not self.quote.currency_code:
            self.note(
                self.env._(
                    "The document does not state its currency, %(currency)s is "
                    "assumed.",
                    currency=self.company.currency_id.name,
                )
            )
        if not converter.is_foreign:
            return
        if converter.error:
            self.incident(
                "currency",
                self.env._(
                    "Document in %(code)s cannot be converted", code=converter.code
                ),
                converter.error
                + " "
                + self.env._(
                    "The order is in %(currency)s with the prices of Odoo; the "
                    "quoted amounts cannot be compared nor used.",
                    currency=self.company.currency_id.name,
                ),
                values={"currency": converter.code, "totals": self.data.get("totals")},
            )
            return
        self.note(
            self.env._(
                "Document in %(code)s, order in %(currency)s. Exchange rate: %(rate)s.",
                code=converter.code,
                currency=self.company.currency_id.name,
                rate=converter.describe(),
            )
        )

    def _payment_term(self, partner):
        """The payment term to apply, ``None`` to keep the one of Odoo."""
        quote = self.quote
        default = self._default_payment_term(partner)
        terms = dict(self.data.get("payment_terms") or {})
        if quote.payment_term_id:
            term = quote.payment_term_id
        elif terms.get("text") or terms.get("days") is not None:
            term = match_payment_term(self.env, self.company, terms)
        else:
            return None
        quoted = terms.get("text") or (
            self.env._("%(days)s days", days=terms["days"])
            if terms.get("days") is not None
            else term.display_name
        )
        if not term:
            self.incident(
                "payment_term",
                self.env._("Payment terms without equivalent in Odoo"),
                self.env._(
                    "The document states '%(quoted)s' and no equivalent payment term "
                    "exists. The default one of the %(role)s (%(default)s) is kept; "
                    "no payment term was created.",
                    quoted=quoted,
                    role=self._role(),
                    default=default.display_name or "-",
                ),
                values=terms,
            )
            self.note(
                self.env._(
                    "Payment terms of the document '%(quoted)s' have no equivalent in "
                    "Odoo: the default ones are kept.",
                    quoted=quoted,
                )
            )
            return None
        if term != default:
            self.note(
                self.env._(
                    "Payment terms: the document states '%(quoted)s', the %(role)s has "
                    "'%(default)s' in Odoo. '%(applied)s' is applied.",
                    quoted=quoted,
                    role=self._role(),
                    default=default.display_name or "-",
                    applied=term.display_name,
                )
            )
        return term

    def _check_delivery_date(self):
        """Validate the quoted delivery date, kept on ``self.delivery_date``."""
        quote = self.quote
        delivery = self.data.get("delivery") or {}
        date = quote.delivery_date
        if delivery.get("date_is_ambiguous"):
            problem = self.env._("the document gives an ambiguous delivery date")
        else:
            problem = self._date_problem(date)
        if problem:
            self.incident(
                "delivery_date",
                self.env._("Delivery date to review"),
                self.env._(
                    "Warning: %(problem)s (%(text)s). The date computed by Odoo is "
                    "used instead.",
                    problem=problem,
                    text=delivery.get("date_text")
                    or (date and self._date(date))
                    or "-",
                ),
                values=delivery,
            )
            self.note(
                self.env._("Delivery date warning: %(problem)s.", problem=problem)
            )
            return
        if date:
            self.delivery_date = date

    def _date_problem(self, date):
        """Why a quoted delivery date cannot be used, or ``None``."""
        quote = self.quote
        if date and quote.quote_date and date < quote.quote_date:
            return self.env._("the delivery date is before the date of the document")
        if date and date < fields.Date.context_today(quote):
            return self.env._("the delivery date is in the past")
        return None

    def _quoted_line_date(self, qline):
        """Delivery date of ``qline`` or of the document, as a datetime, or None."""
        date = qline.delivery_date
        problem = self._date_problem(date)
        if problem:
            self.incident(
                "delivery_date",
                self.env._("Delivery date to review"),
                self.env._(
                    "Warning: %(problem)s (%(text)s). The date computed by Odoo is "
                    "used instead.",
                    problem=problem,
                    text=self._date(date),
                ),
                qline=qline,
            )
            date = None
        date = date or self.delivery_date
        return datetime.combine(date, time(12, 0)) if date else None

    # ------------------------------------------------------------------
    # Lines
    # ------------------------------------------------------------------

    def _global_discount(self):
        discount = self.data.get("global_discount") or {}
        rate, base, error = global_discount_rate(
            discount,
            self.data.get("lines") or [],
            tolerance=self.config.total_tolerance,
        )
        if error:
            reason = {
                "mismatch": self.env._(
                    "its percentage and its amount do not match on a base of %(base)s",
                    base=self._quoted_amount(base),
                ),
                "no_base": self.env._(
                    "it is an amount and the quoted lines lack prices to spread it"
                ),
                "too_large": self.env._("it is larger than the quoted amount"),
            }[error]
            self.discount_pending = True
            self.incident(
                "discount",
                self.env._("Global discount not applied"),
                self.env._(
                    "The global discount of the document (%(percent)s%%, amount "
                    "%(amount)s) cannot be applied safely: %(reason)s.",
                    percent=discount.get("percent") or 0,
                    amount=self._quoted_amount(discount.get("amount")),
                    reason=reason,
                ),
                values=discount,
            )
            return None
        self.global_base = base
        return rate

    def _plan_line(self, qline):
        plan = LinePlan(qline)
        errors = qline.validation_errors
        if not errors and qline.quantity <= 0:
            errors = self.env._("The quantity must be positive.")
        if errors:
            self._line_incident(
                qline,
                "invalid_line",
                self.env._("Incomplete line %(line)s", line=plan.label),
                errors,
            )
            return plan
        if not self._plan_product(plan):
            return plan
        if not self._plan_quantity(plan):
            return plan
        self._plan_prices(plan)
        plan.line_date = self._line_date(qline)
        plan.ok = True
        return plan

    def _line_incident(self, qline, incident_type, name, description):
        qline.write({"state": "pending"})
        self.pending_amount += (
            qline.price_unit * qline.quantity if qline.price_known else 0.0
        )
        self.incident(incident_type, name, description, qline=qline)

    def _plan_product(self, plan):
        qline = plan.qline
        if qline.product_id:
            plan.product = qline.product_id
            if qline.product_match == "manual":
                # Chosen before the partner was known: learn it now.
                self.env["ai.message.import.product.mapping"]._learn(
                    qline, qline.product_id, source="manual"
                )
            elif qline.product_match == "ai":
                self.note(
                    self.env._(
                        "%(line)s: product %(product)s chosen by the AI in a previous "
                        "processing, check it before confirming the order.",
                        line=plan.label,
                        product=qline.product_id.display_name,
                    )
                )
            return True
        match = self._match_product(qline)
        if match.record:
            plan.product = match.record
            qline.write({"product_id": match.record.id, "product_match": match.method})
            return True
        if qline.id in self.ai_choices:
            plan.product = self._use_ai_choice(qline, plan.label)
            return True
        if match.ambiguous:
            self._line_incident(
                qline,
                "product",
                self.env._("Product to choose for %(line)s", line=plan.label),
                self.env._(
                    "Several products match the line: %(names)s. Choose the right "
                    "one on the document line; the choice is learned for this sender "
                    "and %(role)s.",
                    names=", ".join(match.candidates[:10].mapped("display_name")),
                    role=self._role(),
                ),
            )
            return False
        uom = qline.uom_id or self.uoms.resolve(qline.uom_text)
        blocker = self._product_creation_blocker(qline, uom)
        if blocker:
            description = self.env._(
                "No product of Odoo matches the line and it was not created "
                "because %(reason)s. Choose or create the product on the document "
                "line and apply the document again.",
                reason=blocker,
            )
            candidates = self.product_candidates.get(qline.id)
            if candidates:
                description += " " + self.env._(
                    "The most similar ones: %(names)s.",
                    names=", ".join(candidates[:5].mapped("display_name")),
                )
            self._line_incident(
                qline,
                "product",
                self.env._("Product not identified for %(line)s", line=plan.label),
                description,
            )
            return False
        plan.product = self._create_product(qline, uom)
        plan.created_product = True
        return True

    def _use_ai_choice(self, qline, label):
        product, confidence, reason = self.ai_choices[qline.id]
        qline.write({"product_id": product.id, "product_match": "ai"})
        self.note(
            self.env._(
                "%(line)s: product %(product)s chosen by the AI (confidence "
                "%(conf).0f%%), check it before confirming the order. Reason: "
                "%(reason)s",
                line=label,
                product=product.display_name,
                conf=confidence * 100,
                reason=reason,
            )
        )
        return product

    def _propose_products(self):
        """Identify the products of the lines while the partner is unknown: the
        person who chooses it sees them, and the order uses them."""
        self._choose_products()
        for qline in self.quote.line_ids:
            if (
                qline.product_id
                or qline.validation_errors
                or qline.quantity <= 0
                or qline.state == "removed"
            ):
                continue
            match = self._match_product(qline)
            if match.record:
                qline.write(
                    {"product_id": match.record.id, "product_match": match.method}
                )
            elif qline.id in self.ai_choices:
                self._use_ai_choice(qline, LinePlan(qline).label)

    def _match_product(self, qline):
        """The products of the exact rules for ``qline``, searched once."""
        if self._product_matcher is None:
            self._product_matcher = ProductMatcher(
                self.env,
                self.company,
                self.sender,
                self.quote.partner_id,
                ok_field=self.product_ok_field,
                supplier_steps=self.supplier_steps,
            )
        if qline.id not in self.product_matches:
            self.product_matches[qline.id] = self._product_matcher.match(
                self._matching_values(qline)
            )
        return self.product_matches[qline.id]

    def _usual_products(self, partner):
        """``{product: times}`` the partner took each product in its confirmed
        orders of the last year."""
        if not self.confirmed_states or not partner:
            return {}
        since = fields.Datetime.now() - timedelta(days=365)
        groups = self.env[self.line_model]._read_group(
            [
                ("order_id.partner_id", "child_of", partner.commercial_partner_id.id),
                ("order_id.state", "in", list(self.confirmed_states)),
                ("order_id.date_order", ">=", since),
                ("company_id", "=", self.company.id),
                ("product_id", "!=", False),
            ],
            ["product_id"],
            ["__count"],
        )
        return dict(groups)

    def _choose_products(self):
        """Let the AI choose, in one request, the products of the lines that no
        exact rule identified, among the most similar products of Odoo."""
        lines = [
            qline
            for qline in self.quote.line_ids
            if not qline.product_id
            and not qline.validation_errors
            and qline.quantity > 0
            and qline.state != "removed"
            and not self._match_product(qline).record
        ]
        if not lines:
            return
        chooser = ProductChooser(
            self.env,
            self._product_matcher,
            "customer" if self.rank_field == "customer_rank" else "vendor",
            self._usual_products(self.quote.partner_id),
        )
        requests = []
        for qline in lines:
            values = dict(
                self._matching_values(qline),
                uom=qline.uom_text,
                quantity=qline.quantity,
            )
            candidates = chooser.candidates(
                values, self._match_product(qline).candidates
            )
            if candidates:
                self.product_candidates[qline.id] = candidates
                requests.append((qline.id, values, candidates))
        if not requests or not self.config.ai_product_choice:
            return
        try:
            client = self.config._ai_client()
            self.ai_choices = chooser.choose(
                client, requests, self.config.ai_product_min_confidence
            )
        except AIError as error:
            self.note(
                self.env._(
                    "The AI could not choose the products of the lines without an "
                    "exact match (%(error)s): they stay pending.",
                    error=error,
                )
            )
        finally:
            self.quote.conversation_id._add_ai_tokens(chooser.tokens)

    def _matching_values(self, qline):
        return {
            "product_code": qline.product_code,
            "own_code": qline.own_code,
            "barcode": qline.barcode,
            "description": qline.description,
        }

    def _plan_quantity(self, plan):
        """Express the quoted quantity in the unit of the order lines."""
        qline, product = plan.qline, plan.product
        order_uom = self._order_uom(product)
        quantity = qline.quantity
        if plan.created_product or (not qline.uom_text and not qline.uom_id):
            plan.uom, plan.quantity = order_uom, quantity
            if not plan.created_product:
                self.note(
                    self.env._(
                        "%(line)s: the document states no unit, the unit %(uom)s "
                        "of the order is assumed.",
                        line=plan.label,
                        uom=order_uom.name,
                    )
                )
            return True
        uom = qline.uom_id or self.uoms.resolve(qline.uom_text)
        if uom and uom.category_id == product.uom_id.category_id:
            if not qline.uom_id and uom == self.uoms.learned(qline.uom_text):
                self.note(
                    self.env._(
                        "%(line)s: unit '%(text)s' taken as %(uom)s, as learned for "
                        "this sender.",
                        line=plan.label,
                        text=qline.uom_text,
                        uom=uom.name,
                    )
                )
            plan.uom = order_uom
            plan.quantity = uom._compute_quantity(quantity, order_uom, round=False)
            plan.factor = plan.quantity / quantity
            if uom != order_uom:
                self._conversion_note(plan, uom.name, quantity)
            return True
        packaging = self.uoms.packaging(
            product, qline.uom_text, self.company, usage=self.packaging_usage
        )
        if packaging.record:
            plan.packaging = packaging.record
            plan.uom = order_uom
            plan.quantity = packaging.record.product_uom_id._compute_quantity(
                quantity * packaging.record.qty, order_uom, round=False
            )
            plan.factor = plan.quantity / quantity
            self._conversion_note(plan, packaging.record.name, quantity)
            return True
        if uom:
            reason = self.env._(
                "the unit %(uom)s cannot be converted into %(product_uom)s",
                uom=uom.name,
                product_uom=product.uom_id.name,
            )
        elif packaging.ambiguous:
            reason = self.env._(
                "several packagings match it: %(names)s",
                names=", ".join(packaging.candidates.mapped("name")),
            )
        else:
            reason = self.env._("Odoo has no such unit nor packaging for the product")
        self._line_incident(
            qline,
            "uom",
            self.env._(
                "Unit '%(uom)s' of %(line)s", uom=qline.uom_text, line=plan.label
            ),
            self.env._(
                "The quantity %(qty)s %(uom)s cannot be converted: %(reason)s. No "
                "unit nor packaging was created; set the unit on the document line.",
                qty=self._qty(quantity),
                uom=qline.uom_text,
                reason=reason,
            ),
        )
        return False

    def _conversion_note(self, plan, original_uom, quantity):
        self.note(
            self.env._(
                "%(line)s: quoted %(qty)s %(uom)s, conversion factor %(factor)s, "
                "ordered %(final_qty)s %(final_uom)s.",
                line=plan.label,
                qty=self._qty(quantity),
                uom=original_uom,
                factor=float_round(plan.factor, precision_digits=6),
                final_qty=self._qty(plan.quantity),
                final_uom=plan.uom.name,
            )
        )

    def _quoted_price_excluded(self, qline):
        """Quoted unit price without taxes, ``None`` when unknown."""
        if not qline.price_known:
            return None
        if not self.quote.prices_include_tax:
            return qline.price_unit
        if not qline.tax_known:
            return None
        return qline.price_unit / (1 + qline.tax_percent / 100)

    def _plan_prices(self, plan):
        quoted = self.converter.convert(self._quoted_price_excluded(plan.qline))
        if quoted is not None:
            plan.quoted_price = quoted / plan.factor
        if plan.created_product:
            plan.price_unit = plan.quoted_price

    def _line_discount(self, line, plan):
        """Discount of the line: the quoted one, or the one of Odoo, combined
        with the global discount of the quote."""
        qline = plan.qline
        # The discount of Odoo comes from its price lists, never from the line:
        # it may already hold the global discount of a former application.
        odoo_discount = self._odoo_discount(line)
        base = qline.discount_percent or odoo_discount
        if (
            qline.discount_percent
            and not float_is_zero(odoo_discount, precision_digits=2)
            and float_compare(odoo_discount, qline.discount_percent, precision_digits=2)
        ):
            self.note(
                self.env._(
                    "%(line)s: the quoted discount %(quoted)s%% replaces the "
                    "discount of %(odoo)s%% of the price list.",
                    line=plan.label,
                    quoted=qline.discount_percent,
                    odoo=odoo_discount,
                )
            )
        if self.global_rate:
            return combine_discounts(base, self.global_rate)
        return base

    def _apply_lines(self, order, plans):
        ai_lines = order.order_line.filtered(
            lambda line: line.ai_message_import_line_kind == "product"
            and not line.display_type
        )
        removed = order.ai_message_import_document_ids.line_ids.filtered(
            lambda qline: qline.state == "removed"
        )
        used = self.env[self.line_model]
        valid = [plan for plan in plans if plan.ok]
        # The lines of the order that a line pending review refers to are kept
        # as they are: they are neither updated nor removed.
        for plan in plans:
            if not plan.ok:
                used |= self._existing_line(plan, ai_lines - used) or used.browse()
        for plan in valid:
            self._check_pack_size(order, plan)
            line = self._existing_line(plan, ai_lines - used)
            if line:
                used |= line
                self._update_line(line, plan)
            elif self._removed_by_person(plan, removed):
                continue
            else:
                line = self._create_line(order, plan)
            plan.qline.write({self.line_link: line.id, "state": "applied"})
            self._check_line_price(line, plan)
            self._check_line_taxes(line, plan)
        if self.quote.relation == "update" or self._quote_order():
            self._handle_missing_lines(
                ai_lines - used, complete=len(valid) == len(plans)
            )

    @staticmethod
    def _pack_sizes(product, qline):
        """The units a box may hold: the numbers of the name of the product
        ("... APROX144", "... 144 UNDS") and of the line ("... 78U/C"), and the
        contents of the packagings of the product."""
        texts = (product.name or "", qline.description or "")
        sizes = {int(number) for text in texts for number in NAME_NUMBER.findall(text)}
        sizes |= {
            int(qty) for qty in product.packaging_ids.mapped("qty") if qty == int(qty)
        }
        return sorted(size for size in sizes if size >= 2)

    def _check_pack_size(self, order, plan):
        """Count in the unit of Odoo a quantity the document gives in the units
        of a box, or the other way round.

        "288 UD at 0.481" of a product that Odoo sells by box of 144 at 69.34:
        the price of Odoo is 144 times the quoted one, and 144 is written in the
        name of the product or in the line, or is the content of one of its
        packagings. Only when both agree the quantity becomes 2 boxes; a
        quantity that is no whole number of boxes is ordered too, with an
        incident to check it.
        """
        qline = plan.qline
        if (
            plan.created_product
            or plan.packaging
            or qline.uom_id
            or not plan.quoted_price
            or plan.quoted_price <= 0
        ):
            return
        # The price of Odoo for the line, as the line would get it.
        odoo_price = (
            self.env[self.line_model].new(self._line_values(order, plan)).price_unit
        )
        if odoo_price <= 0:
            return
        ratio = odoo_price / plan.quoted_price
        for size in self._pack_sizes(plan.product, qline):
            if abs(ratio - size) <= size * PACK_PRICE_TOLERANCE:
                # The document counts the units of the box Odoo sells.
                factor = 1 / size
            elif abs(1 / ratio - size) <= size * PACK_PRICE_TOLERANCE:
                # The document counts boxes of the units Odoo sells.
                factor = size
            else:
                continue
            break
        else:
            return
        quantity = plan.quantity
        plan.quantity = quantity * factor
        plan.factor *= factor
        plan.quoted_price /= factor
        values = {
            "line": plan.label,
            "size": size,
            "qty": self._qty(quantity),
            "uom": qline.uom_text or plan.uom.name,
            "final_qty": self._qty(plan.quantity),
            "final_uom": plan.uom.name,
        }
        if factor < 1:
            note = self.env._(
                "%(line)s: the price of Odoo is %(size)s times the quoted one and "
                "a box holds %(size)s units, so the document counts its units: "
                "%(qty)s %(uom)s ordered as %(final_qty)s %(final_uom)s.",
                **values,
            )
        else:
            note = self.env._(
                "%(line)s: the quoted price is %(size)s times the one of Odoo and "
                "a box holds %(size)s units, so the document counts boxes: "
                "%(qty)s %(uom)s ordered as %(final_qty)s %(final_uom)s.",
                **values,
            )
        self.note(note)
        if not float_is_zero(plan.quantity - round(plan.quantity), precision_digits=3):
            self.incident(
                "pack_size",
                self.env._("Quantity of %(line)s to check", line=plan.label),
                self.env._(
                    "The document gives %(qty)s %(uom)s and a box holds %(size)s "
                    "of them: %(final_qty)s %(final_uom)s, not a whole number. "
                    "Check the quantity of the order line.",
                    qty=self._qty(quantity),
                    uom=qline.uom_text or plan.uom.name,
                    size=size,
                    final_qty=self._qty(plan.quantity),
                    final_uom=plan.uom.name,
                ),
                qline=qline,
            )

    def _removed_by_person(self, plan, removed):
        """Whether a person removed this line from the order before."""
        qline = plan.qline
        code = normalize_code(qline.product_code)
        text = normalize_text(qline.description)
        match = removed.filtered(
            lambda r: (
                r == qline
                or r.product_id == plan.product
                or (code and normalize_code(r.product_code) == code)
                or (text and normalize_text(r.description) == text)
            )
        )
        if not match:
            return False
        self.incident(
            "human_conflict",
            self.env._("Line removed by a person: %(line)s", line=plan.label),
            self.env._(
                "A person removed this line from the order. The document includes it "
                "again but it was not added back: add it by hand if it is needed."
            ),
            qline=qline,
        )
        self.note(
            self.env._(
                "%(line)s was removed by a person and was not added again.",
                line=plan.label,
            )
        )
        qline.write({"state": "removed"})
        return True

    def _existing_line(self, plan, lines):
        by_quote_line = lines.filtered(
            lambda line: line.ai_message_import_document_line_id == plan.qline
        )
        if by_quote_line:
            return by_quote_line[:1]
        if plan.product:
            by_product = lines.filtered(lambda line: line.product_id == plan.product)
            if len(by_product) == 1:
                return by_product
        code = normalize_code(plan.qline.product_code)
        text = normalize_text(plan.qline.description)
        for line in lines:
            source = line.ai_message_import_document_line_id
            if (code and normalize_code(source.product_code) == code) or (
                text and normalize_text(source.description) == text
            ):
                return line
        return None

    def _create_line(self, order, plan):
        line = self.env[self.line_model].create(self._line_values(order, plan))
        # The default values of a new line are computed for a quantity of 1:
        # compute again the prices of Odoo for the real quantity.
        self._recompute_line_prices(line)
        updates = {"discount": self._line_discount(line, plan)}
        if plan.price_unit is not None:
            updates["price_unit"] = plan.price_unit
        if plan.line_date and self.line_date_field:
            updates[self.line_date_field] = plan.line_date
        line.write(updates)
        if self.line_date_field and not plan.line_date:
            self._computed_date_note(line, plan)
        line.ai_message_import_ai_values = self._line_snapshot(line)
        self.changes.append(
            {
                self.line_link: line.id,
                "operation": "create",
                "field_label": self.env._("Line"),
                "new_value": self._describe_line(line),
            }
        )
        return line

    def _describe_line(self, line):
        return self.env._(
            "%(product)s: %(qty)s %(uom)s at %(price)s, discount %(discount)s%%",
            product=line.product_id.display_name,
            qty=self._qty(line[self.qty_field]),
            uom=line.product_uom.name,
            price=self._amount(line.price_unit, line.currency_id),
            discount=float_round(line.discount, precision_digits=2),
        )

    @staticmethod
    def _plain(value):
        """A value of a field as stored in the snapshots."""
        if isinstance(value, datetime):
            return fields.Datetime.to_string(value)
        if isinstance(value, date):
            return fields.Date.to_string(value)
        if hasattr(value, "_name"):
            return value.id
        return value

    def _field_value(self, record, name):
        return self._plain(record[name])

    def _line_snapshot(self, line):
        return {name: self._field_value(line, name) for name in self.line_fields}

    def _same(self, record, name, value):
        return self._equal(record, name, self._field_value(record, name), value)

    def _equal(self, record, name, first, second):
        first, second = self._plain(first), self._plain(second)
        if record._fields[name].type == "float":
            digits = record._fields[name].get_digits(self.env)
            precision = digits[1] if digits else 6
            return (
                float_compare(first or 0.0, second or 0.0, precision_digits=precision)
                == 0
            )
        return (first or False) == (second or False)

    def _update_line(self, line, plan):
        """Update an existing line, sparing the fields changed by a person."""
        snapshot = dict(line.ai_message_import_ai_values or {})
        touched = {
            name
            for name in self.line_fields
            if name in snapshot and not self._same(line, name, snapshot[name])
        }
        before = {name: self._field_value(line, name) for name in self.line_fields}
        human = {name: before[name] for name in touched}
        conflicts = self._update_quantity(line, plan, touched)
        conflicts += self._update_terms(line, plan, touched, human)
        # A recomputation triggered by a new quantity must not undo a change
        # made by a person either.
        restore = {
            name: value
            for name, value in human.items()
            if not self._same(line, name, value)
        }
        for name in restore:
            if line._fields[name].type == "datetime":
                restore[name] = fields.Datetime.to_datetime(restore[name])
        if restore:
            line.write(restore)
        after = self._line_snapshot(line)
        self._record_line_changes(line, before, after)
        # The fields of a person stay different from the snapshot, so they
        # remain protected on the next update.
        line.ai_message_import_ai_values = dict(
            after, **{name: snapshot[name] for name in touched}
        )
        line.ai_message_import_document_line_id = plan.qline
        for name in set(conflicts):
            self._conflict(line, name, plan)

    def _update_quantity(self, line, plan, touched):
        """Set the product, quantity and unit; :return: the conflicting fields."""
        target = {
            "product_id": plan.product.id,
            self.qty_field: plan.quantity,
            "product_uom": plan.uom.id,
            "product_packaging_id": self._target_packaging(line, plan),
        }
        changed = {
            name: value
            for name, value in target.items()
            if not self._same(line, name, value)
        }
        if not changed:
            return []
        # Product, quantity, unit and packaging only make sense together: when a
        # person changed one of them, none is written.
        if touched & set(target):
            return list(changed)
        if "product_id" in changed:
            # Start from the new product, as Odoo does when it is selected.
            self._change_line_product(line, changed["product_id"])
        line.write(changed)
        # Prices and dates of Odoo for the new quantity.
        self._recompute_line_prices(line)
        return []

    def _target_packaging(self, line, plan):
        """Packaging of the line: the quoted one, if any."""
        return plan.packaging.id if plan.packaging else False

    def _update_terms(self, line, plan, touched, human):
        """Set the discount, explicit price and date; :return: the conflicts."""
        target = {"discount": self._line_discount(line, plan)}
        if plan.price_unit is not None:
            target["price_unit"] = plan.price_unit
        if plan.line_date and self.line_date_field:
            target[self.line_date_field] = plan.line_date
        conflicts = []
        for name, value in target.items():
            if name not in touched:
                line[name] = value
            elif not self._equal(line, name, human[name], value):
                conflicts.append(name)
        return conflicts

    def _record_line_changes(self, line, before, after):
        for name in self.line_fields:
            if self._equal(line, name, after[name], before[name]):
                continue
            self.changes.append(
                {
                    self.line_link: line.id,
                    "operation": "update",
                    "field_name": name,
                    "field_label": line._fields[name].get_description(self.env)[
                        "string"
                    ],
                    "old_value": self._display(line, name, before[name]),
                    "new_value": self._display(line, name, after[name]),
                }
            )

    def _display(self, record, name, value):
        field = record._fields[name]
        if field.type == "many2one":
            return self.env[field.comodel_name].browse(value).display_name or ""
        if value is False or value is None:
            return ""
        return str(value)

    def _conflict(self, record, name, plan=None):
        label = record._fields[name].get_description(self.env)["string"]
        where = plan.label if plan else record.display_name
        self.incident(
            "human_conflict",
            self.env._(
                "Manual change kept: %(field)s of %(where)s", field=label, where=where
            ),
            self.env._(
                "A person changed '%(field)s' after the last automatic update. The "
                "new document also changes it, so the field was not overwritten: "
                "decide which value is right.",
                field=label,
            ),
            qline=plan.qline if plan else None,
        )
        self.note(
            self.env._(
                "Conflict: '%(field)s' of %(where)s was changed by a person and "
                "was not overwritten.",
                field=label,
                where=where,
            )
        )

    def _handle_missing_lines(self, lines, complete=True):
        """Lines of the order absent from the quote.

        They are only removed when the quote replaces the previous one and all
        its lines could be processed; otherwise they are kept.
        """
        if not lines:
            return
        remove = (
            complete
            and self.quote.relation == "update"
            and self.quote.remove_missing_lines
        )
        for line in lines:
            snapshot = line.ai_message_import_ai_values or {}
            changed = [
                name
                for name in self.line_fields
                if name in snapshot and not self._same(line, name, snapshot[name])
            ]
            if not remove:
                if self.quote.relation == "update":
                    self.note(
                        self.env._(
                            "%(line)s is not in the correction and was kept.",
                            line=line.product_id.display_name,
                        )
                    )
                continue
            if changed:
                self._conflict(line, changed[0])
                continue
            self.changes.append(
                {
                    "operation": "delete",
                    "field_label": self.env._("Line"),
                    "old_value": self._describe_line(line),
                }
            )
            self.note(
                self.env._(
                    "%(line)s removed: the new document replaces the previous one.",
                    line=self._describe_line(line),
                )
            )
            line.unlink()

    def _check_line_price(self, line, plan):
        if plan.created_product:
            return
        self._check_zero_price(line, plan)
        if plan.quoted_price is None:
            return
        difference = line.price_unit - plan.quoted_price
        # The amount of the line is compared, with its discount: a difference
        # too small for a unit price adds up on a large quantity.
        line_difference = difference * line[self.qty_field] * (1 - line.discount / 100)
        if float_is_zero(line_difference, precision_rounding=line.currency_id.rounding):
            return
        self.price_difference += line_difference
        self.note(
            self.env._(
                "%(line)s: quoted price %(quoted)s, Odoo price (%(origin)s) "
                "%(odoo)s; the Odoo price is applied. Difference %(diff)s per "
                "%(uom)s, %(total)s for the line.",
                line=plan.label,
                quoted=self._price(plan.quoted_price),
                origin=self._price_origin(line),
                odoo=self._price(line.price_unit),
                diff=self._price(difference),
                uom=line.product_uom.name,
                total=self._amount(line_difference),
            )
        )

    def _tax_rate(self, line):
        taxes = line[self.tax_field]
        if not taxes:
            return None
        result = taxes.compute_all(
            100.0,
            currency=line.currency_id,
            quantity=1.0,
            product=line.product_id,
            partner=line.order_id.partner_id,
        )
        excluded = result["total_excluded"]
        if not excluded:
            return 0.0
        return (result["total_included"] - excluded) / excluded * 100

    def _check_line_taxes(self, line, plan):
        qline = plan.qline
        rate = self._tax_rate(line)
        # Formatted out of the translated texts: their extraction reads no
        # f-strings.
        quoted = format(qline.tax_percent, "g")
        if rate is None:
            self.tax_issue = True
            self.incident(
                "tax_missing",
                self.env._("Line without tax: %(line)s", line=plan.label),
                self.env._(
                    "Odoo has no tax for %(product)s on this %(order)s, so the line "
                    "has no tax for now. It is NOT considered exempt: set the right "
                    "tax before confirming. Tax of the document: %(quoted)s.",
                    product=line.product_id.display_name,
                    order=self._order_label(),
                    quoted=quoted + "%" if qline.tax_known else "-",
                ),
                qline=qline,
            )
            self.note(
                self.env._(
                    "%(line)s has no tax pending review (not considered exempt).",
                    line=plan.label,
                )
            )
            return
        if not qline.tax_known:
            return
        if float_compare(rate, qline.tax_percent, precision_digits=2):
            self.tax_issue = True
            taxes = ", ".join(line[self.tax_field].mapped("name"))
            self.incident(
                "tax_difference",
                self.env._("Different tax for %(line)s", line=plan.label),
                self.env._(
                    "The document states a tax of %(quoted)s%%, Odoo applies "
                    "%(taxes)s (%(rate)s%%). The taxes of Odoo are kept.",
                    quoted=quoted,
                    taxes=taxes,
                    rate=format(rate, "g"),
                ),
                qline=qline,
            )
            self.note(
                self.env._(
                    "%(line)s: tax of the document %(quoted)s%%, tax of Odoo %(taxes)s "
                    "kept.",
                    line=plan.label,
                    quoted=quoted,
                    taxes=taxes,
                )
            )

    # ------------------------------------------------------------------
    # Freight, discount and totals
    # ------------------------------------------------------------------

    def _apply_freight(self, order):
        shipping = self.data.get("shipping") or {}
        amount = shipping.get("amount")
        line = order.order_line.filtered(
            lambda line: line.ai_message_import_line_kind == "freight"
        )[:1]
        if not amount:
            return
        product = self.config.freight_product_id
        converted = self.converter.convert(amount)
        if not product or converted is None:
            self.freight_pending = True
            reason = (
                self.env._("no transport product is configured")
                if not product
                else self.converter.error
            )
            self.incident(
                "freight",
                self.env._("Transport charges pending"),
                self.env._(
                    "The document charges %(amount)s for transport (%(description)s) "
                    "and no line was added because %(reason)s. Configure a "
                    "service product for transport in the settings and add the "
                    "line; no product was created.",
                    amount=self._quoted_amount(amount),
                    description=shipping.get("description") or "-",
                    reason=reason,
                ),
                values=shipping,
            )
            self.note(
                self.env._(
                    "Transport charges of %(amount)s pending review.",
                    amount=self._quoted_amount(amount),
                )
            )
            return
        if self.quote.prices_include_tax:
            rate = self._freight_tax_rate(product, order)
            converted = converted / (1 + rate / 100)
        if line:
            snapshot = line.ai_message_import_ai_values or {}
            if "price_unit" in snapshot and not self._same(
                line, "price_unit", snapshot["price_unit"]
            ):
                if not self._same(line, "price_unit", converted):
                    self._conflict(line, "price_unit")
                return
            if not self._same(line, "price_unit", converted):
                self.changes.append(
                    {
                        self.line_link: line.id,
                        "operation": "update",
                        "field_name": "price_unit",
                        "field_label": self.env._("Transport"),
                        "old_value": str(line.price_unit),
                        "new_value": str(converted),
                    }
                )
                line.price_unit = converted
        else:
            line = self.env[self.line_model].create(
                self._freight_line_values(order, product, converted)
            )
            line.write({"price_unit": converted, "discount": 0.0})
        line.ai_message_import_ai_values = self._line_snapshot(line)
        self.note(
            self.env._(
                "Transport charges: %(amount)s on the line %(product)s, with the "
                "taxes of Odoo.",
                amount=self._amount(converted),
                product=product.display_name,
            )
        )

    def _document_discount(self, order, plans):
        if not self.global_rate:
            return
        discount = self.data.get("global_discount") or {}
        precision = self.env["decimal.precision"].precision_get("Discount")
        expected = applied = 0.0
        details = []
        for plan in plans:
            line = plan.qline[self.line_link]
            if not line:
                continue
            gross = line.price_unit * line[self.qty_field]
            base_discount = (
                plan.qline.discount_percent
                if plan.qline.discount_percent
                else self._odoo_discount(line)
            )
            before_global = gross * (1 - base_discount / 100)
            expected += before_global * self.global_rate / 100
            applied += before_global - line.price_subtotal
            details.append(
                self.env._(
                    "%(line)s %(discount)s%%",
                    line=plan.label,
                    discount=float_round(line.discount, precision_digits=precision),
                )
            )
        self.note(
            self.env._(
                "Global discount of the document: %(percent)s%% / %(amount)s on a base "
                "of %(base)s. Spread proportionally on the net amount of each valid "
                "line (same rate %(rate)s%% on each one, combined with its own "
                "discount): %(details)s. Transport is not discounted.",
                percent=discount.get("percent") or "-",
                amount=self._quoted_amount(discount.get("amount"))
                if discount.get("amount")
                else "-",
                base=self._quoted_amount(self.global_base)
                if self.global_base is not None
                else "-",
                rate=float_round(self.global_rate, precision_digits=4),
                details="; ".join(details),
            )
        )
        residual = applied - expected
        if not float_is_zero(residual, precision_rounding=order.currency_id.rounding):
            self.note(
                self.env._(
                    "Rounding of the discount percentages: %(residual)s compared to "
                    "an exact spread (%(expected)s expected, %(applied)s applied).",
                    residual=self._amount(residual),
                    expected=self._amount(expected),
                    applied=self._amount(applied),
                )
            )
        quoted = discount.get("amount") or (
            self.global_base * self.global_rate / 100 if self.global_base else None
        )
        converted = self.converter.convert(quoted)
        if converted is not None and not float_is_zero(
            converted - applied, precision_rounding=order.currency_id.rounding
        ):
            self.note(
                self.env._(
                    "The global discount amounts to %(applied)s on the order and "
                    "%(quoted)s on the document, because the order uses the prices of "
                    "Odoo and only the valid lines.",
                    applied=self._amount(applied),
                    quoted=self._amount(converted),
                )
            )

    def _check_totals(self, order):
        totals = self.data.get("totals") or {}
        tolerance = self.config.total_tolerance
        comparisons = []
        for key, field_name, label in (
            ("untaxed", "amount_untaxed", self.env._("untaxed")),
            ("total", "amount_total", self.env._("total")),
        ):
            quoted = totals.get(key)
            if quoted is None:
                continue
            converted = self.converter.convert(quoted)
            if converted is None:
                continue
            difference = converted - order[field_name]
            if abs(difference) > tolerance:
                comparisons.append(
                    (label, quoted, converted, order[field_name], difference)
                )
        if not comparisons:
            return
        causes = []
        if self.pending_amount or self.quote.line_ids.filtered(
            lambda line: line.state == "pending"
        ):
            causes.append(self.env._("lines pending review are not on the order"))
        if not float_is_zero(self.price_difference, precision_digits=2):
            causes.append(
                self.env._(
                    "the prices of Odoo differ from the quoted ones by %(amount)s",
                    amount=self._amount(self.price_difference),
                )
            )
        if self.tax_issue:
            causes.append(self.env._("the taxes differ or are missing"))
        if self.freight_pending:
            causes.append(self.env._("the transport charges are pending"))
        if self.discount_pending:
            causes.append(self.env._("the global discount was not applied"))
        if self.converter.is_foreign:
            causes.append(self.env._("currency conversion"))
        if not causes:
            causes.append(self.env._("rounding or data not identified"))
        lines = [
            self.env._(
                "Document %(label)s %(quoted)s (%(converted)s), order %(order)s, "
                "difference %(difference)s.",
                label=label,
                quoted=self._quoted_amount(quoted),
                converted=self._amount(converted),
                order=self._amount(amount),
                difference=self._amount(difference),
            )
            for label, quoted, converted, amount, difference in comparisons
        ]
        description = (
            "\n".join(lines)
            + "\n"
            + self.env._("Possible causes: %(causes)s.", causes="; ".join(causes))
            + "\n"
            + self.env._(
                "No price was changed and no line was added to match the totals."
            )
        )
        self.incident(
            "total_difference",
            self.env._("Totals differ from the document"),
            description,
            values=totals,
        )
        self.note(description)

    # ------------------------------------------------------------------
    # Order creation and update
    # ------------------------------------------------------------------

    def _create_order(self, partner, header):
        values = self._order_values(partner, header)
        values.update(header)
        order = self.env[self.order_model].create(values)
        order.ai_message_import_ai_values = {
            name: self._field_value(order, name) for name in self.order_fields
        }
        self.changes.append(
            {
                "operation": "create",
                "field_label": self._order_label().capitalize(),
                "new_value": order.name,
            }
        )
        return order

    def _update_order(self, order, header):
        snapshot = dict(order.ai_message_import_ai_values or {})
        new_snapshot = dict(snapshot)
        for name, value in header.items():
            if self._same(order, name, value):
                continue
            if name in snapshot and not self._same(order, name, snapshot[name]):
                self._conflict(order, name)
                continue
            old = self._display(order, name, self._field_value(order, name))
            order[name] = value
            new_snapshot[name] = self._field_value(order, name)
            self.changes.append(
                {
                    "operation": "update",
                    "field_name": name,
                    "field_label": order._fields[name].get_description(self.env)[
                        "string"
                    ],
                    "old_value": old,
                    "new_value": self._display(order, name, new_snapshot[name]),
                }
            )
        order.ai_message_import_ai_values = new_snapshot

    # ------------------------------------------------------------------
    # Result
    # ------------------------------------------------------------------

    def _finish(self, order, state):
        quote = self.quote
        Incident = self.env["mail.message.import.incident"]
        common = {
            "document_id": quote.id,
            "conversation_id": quote.conversation_id.id,
            "sender_id": quote.sender_id.id,
            "company_id": quote.company_id.id,
            "channel_id": quote.channel_id.id,
            self.order_link: order.id if order else False,
        }
        incidents = Incident.create(
            [dict(common, **values) for values in self.incidents]
        )
        for incident in incidents.filtered("document_line_id"):
            incident[self.line_link] = incident.document_line_id[self.line_link]
        reference = self.env._(
            "Document %(quote)s received on %(channel)s (conversation "
            "%(conversation)s, processing %(run)s)",
            quote=quote.name,
            channel=quote.channel_id.name or "-",
            conversation=quote.conversation_id.name or "-",
            run=quote.processing_ref or "-",
        )
        body = Markup("<p><strong>%s</strong></p>") % reference
        if self.notes:
            body += Markup("<ul>%s</ul>") % Markup().join(
                Markup("<li>%s</li>") % note for note in self.notes
            )
        if incidents:
            body += Markup("<p>%s</p>") % self.env._(
                "%(count)s incident(s) pending review.", count=len(incidents)
            )
        values = {"state": state, "processing_notes": body}
        if order and state == "done":
            values[self.order_link] = order.id
        quote.write(values)
        if order and state == "done":
            self._post_order_note(order, body)
            self._record_changes(order)
        return order

    def _post_order_note(self, order, body):
        quote = self.quote
        attachments = self.env["ir.attachment"]
        known = set(order.message_ids.attachment_ids.mapped("checksum"))
        for attachment in quote.attachment_ids:
            if attachment.checksum not in known:
                attachments |= attachment.copy(
                    {"res_model": self.order_model, "res_id": order.id}
                )
        order.message_post(
            body=body,
            author_id=note_author(self.env).id,
            subtype_xmlid="mail.mt_note",
            message_type="comment",
            attachment_ids=attachments.ids,
        )

    def _record_changes(self, order):
        quote = self.quote
        reason = quote.relation_reason or "\n".join(quote.clarification_list())
        self.env["ai.message.import.change"].create(
            [
                dict(
                    {
                        "document_id": quote.id,
                        "conversation_id": quote.conversation_id.id,
                        "sender_id": quote.sender_id.id,
                        "company_id": quote.company_id.id,
                        self.order_link: order.id,
                        "processing_ref": quote.processing_ref,
                        "reason": reason,
                        "message_ids": [(6, 0, quote.message_ids.ids)],
                    },
                    **change,
                )
                for change in self.changes
            ]
        )
