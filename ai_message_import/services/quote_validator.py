# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Validation of the answers of the AI against ``quote_schema``.

Nothing coming from the AI is used before going through ``validate_response``:
the structure, the types, the ranges and the references are checked, the texts
are cleaned and bounded. A broken structure rejects the whole answer; a wrong
value only invalidates its line, which is then reviewed by a person.
"""

import re
from datetime import date

from odoo import _

from .quote_schema import SCHEMA_VERSION
from .tools import clean_text

MAX_QUOTES = 20
MAX_LINES = 500
MAX_TEXT = 2000
MAX_QUANTITY = 1e9
MAX_AMOUNT = 1e10
RELATIONS = ("new", "update", "duplicate")
CURRENCY_CODE = re.compile(r"^[A-Z]{3}$")
COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")


class AIResponseError(Exception):
    """The answer does not follow the contract and cannot be used at all."""


def parse_number(value):
    """A float from a JSON number, or from a number written as text."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str):
        return None
    text = re.sub(r"[^\d,.\-]", "", value)
    if "," in text and "." in text:
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        text = text.replace(thousands, "").replace(decimal, ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_date(value):
    """The ISO text of a plausible date, ``None`` otherwise."""
    text = clean_text(value)[:10]
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return None
    return parsed.isoformat() if 2000 <= parsed.year <= 2100 else None


class _QuoteValidator:
    def __init__(
        self, env, message_labels, document_labels, target_references, document_types
    ):
        self.env = env
        self.message_labels = set(message_labels)
        self.document_labels = set(document_labels)
        self.target_references = set(target_references)
        self.document_types = (
            set(document_types) if document_types is not None else None
        )

    def number(self, value, warnings, field, minimum=0.0, maximum=MAX_AMOUNT):
        if value is None:
            return None
        number = parse_number(value)
        if number is None or not minimum <= number <= maximum:
            warnings.append(
                _(
                    "Ignored invalid value for %(field)s: %(value)r.",
                    field=field,
                    value=value,
                )
            )
            return None
        return number

    def confidence(self, value):
        number = parse_number(value)
        if number is None:
            return 0.0
        return min(max(number, 0.0), 1.0)

    def text(self, value, length=MAX_TEXT):
        return clean_text(value, length)

    def texts(self, values, length=MAX_TEXT):
        if not isinstance(values, list):
            return []
        return [text for text in (self.text(v, length) for v in values[:50]) if text]

    def refs(self, values, allowed, warnings):
        refs = []
        for ref in self.texts(values, 20):
            if ref in allowed:
                refs.append(ref)
            else:
                warnings.append(_("Ignored unknown reference %(ref)s.", ref=ref))
        return refs

    def dict_field(self, data, key):
        value = data.get(key)
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise AIResponseError(_("'%(key)s' must be an object.", key=key))
        return value

    def line(self, data, index):
        if not isinstance(data, dict):
            raise AIResponseError(_("Line %(index)s is not an object.", index=index))
        errors, warnings = [], []
        line = {
            "sequence": index,
            "product_code": self.text(data.get("product_code"), 128),
            "own_code": self.text(data.get("own_code"), 128),
            "barcode": re.sub(r"\D", "", self.text(data.get("barcode"), 64)),
            "description": self.text(data.get("description"), 1000),
            "uom": self.text(data.get("uom"), 64),
            "is_service": data.get("is_service") is True,
            "confidence": self.confidence(data.get("confidence")),
        }
        quantity = parse_number(data.get("quantity"))
        if quantity is None or not 0 < quantity <= MAX_QUANTITY:
            errors.append(_("Invalid quantity: %(qty)r.", qty=data.get("quantity")))
            quantity = None
        line["quantity"] = quantity
        if not (
            line["description"]
            or line["product_code"]
            or line["own_code"]
            or line["barcode"]
        ):
            errors.append(_("The line has neither description nor reference."))
        line["price_unit"] = self.number(data.get("price_unit"), warnings, _("price"))
        line["discount_percent"] = self.number(
            data.get("discount_percent"),
            warnings,
            _("discount"),
            maximum=100.0,
        )
        line["subtotal"] = self.number(data.get("subtotal"), warnings, _("subtotal"))
        line["tax_percent"] = self.number(
            data.get("tax_percent"), warnings, _("tax"), maximum=100.0
        )
        line["delivery_date"] = parse_date(data.get("delivery_date"))
        if data.get("delivery_date") and not line["delivery_date"]:
            warnings.append(
                _("Invalid delivery date: %(date)r.", date=data.get("delivery_date"))
            )
        line["errors"] = errors
        line["warnings"] = warnings
        return line

    def quote(self, data, index):
        if not isinstance(data, dict):
            raise AIResponseError(
                _("Document %(index)s is not an object.", index=index)
            )
        lines = data.get("lines")
        if not isinstance(lines, list):
            raise AIResponseError(
                _("Document %(index)s has no list of lines.", index=index)
            )
        if len(lines) > MAX_LINES:
            raise AIResponseError(
                _("Document %(index)s has too many lines.", index=index)
            )
        document_type = self.text(data.get("document_type"), 32)
        if self.document_types is not None and document_type not in self.document_types:
            raise AIResponseError(
                _(
                    "Document %(index)s has an unknown document type %(type)r.",
                    index=index,
                    type=document_type,
                )
            )
        warnings = self.texts(data.get("warnings"))
        relation = data.get("relation")
        if relation not in RELATIONS:
            warnings.append(
                _(
                    "Unknown relation %(relation)r, handled as new.",
                    relation=relation,
                )
            )
            relation = "new"
        target = self.text(data.get("target_reference"), 64) or None
        if target and target not in self.target_references:
            warnings.append(
                _("Ignored unknown previous quotation %(target)s.", target=target)
            )
            target = None
        partner = self.dict_field(data, "partner")
        country = self.text(partner.get("country_code"), 8).upper()
        terms = self.dict_field(data, "payment_terms")
        delivery = self.dict_field(data, "delivery")
        discount = self.dict_field(data, "global_discount")
        shipping = self.dict_field(data, "shipping")
        totals = self.dict_field(data, "totals")
        currency = self.text(data.get("currency"), 8).upper()
        if currency and not CURRENCY_CODE.match(currency):
            warnings.append(
                _("Ignored invalid currency %(currency)r.", currency=currency)
            )
            currency = ""
        days = terms.get("days")
        if days is not None:
            days = parse_number(days)
            days = int(days) if days is not None and 0 <= days <= 730 else None
        quote = {
            "quote_key": self.text(data.get("quote_key"), 32) or f"Q{index}",
            "document_type": document_type,
            "relation": relation,
            "target_reference": target,
            "relation_reason": self.text(data.get("relation_reason")),
            "remove_missing_lines": data.get("remove_missing_lines") is True,
            "message_refs": self.refs(
                data.get("message_refs"), self.message_labels, warnings
            ),
            "document_refs": self.refs(
                data.get("document_refs"), self.document_labels, warnings
            ),
            "partner": {
                "name": self.text(partner.get("name"), 256),
                "vat": self.text(partner.get("vat"), 32),
                "email": self.text(partner.get("email"), 256),
                "phone": self.text(partner.get("phone"), 64),
                "street": self.text(partner.get("street"), 256),
                "city": self.text(partner.get("city"), 128),
                "zip": self.text(partner.get("zip"), 16),
                "country_code": country if COUNTRY_CODE.match(country) else "",
                "confidence": self.confidence(partner.get("confidence")),
            },
            "quote_number": self.text(data.get("quote_number"), 64),
            "quote_date": parse_date(data.get("quote_date")),
            "currency": currency,
            "prices_include_tax": data.get("prices_include_tax") is True,
            "payment_terms": {
                "text": self.text(terms.get("text"), 256),
                "days": days,
                "end_of_month": terms.get("end_of_month") is True,
            },
            "delivery": {
                "date": parse_date(delivery.get("date")),
                "date_text": self.text(delivery.get("date_text"), 256),
                "date_is_ambiguous": delivery.get("date_is_ambiguous") is True,
                "address": self.text(delivery.get("address"), 512),
            },
            "global_discount": {
                "percent": self.number(
                    discount.get("percent"),
                    warnings,
                    _("global discount"),
                    0.0,
                    100.0,
                ),
                "amount": self.number(
                    discount.get("amount"),
                    warnings,
                    _("global discount amount"),
                ),
                "description": self.text(discount.get("description"), 256),
            },
            "shipping": {
                "amount": self.number(shipping.get("amount"), warnings, _("shipping")),
                "description": self.text(shipping.get("description"), 256),
            },
            "totals": {
                key: self.number(totals.get(key), warnings, _("totals"))
                for key in ("untaxed", "tax", "total")
            },
            "clarifications": self.texts(data.get("clarifications")),
            "warnings": warnings,
            "confidence": self.confidence(data.get("confidence")),
        }
        if delivery.get("date") and not quote["delivery"]["date"]:
            quote["delivery"]["date_is_ambiguous"] = True
            warnings.append(
                _("Invalid delivery date: %(date)r.", date=delivery.get("date"))
            )
        quote["lines"] = [
            self.line(line, position) for position, line in enumerate(lines, 1)
        ]
        return quote

    def response(self, data):
        """The answer ``data`` checked and normalised, see ``validate_response``."""
        if not isinstance(data, dict):
            raise AIResponseError(_("The answer is not a JSON object."))
        if data.get("schema_version") != SCHEMA_VERSION:
            raise AIResponseError(
                _(
                    "Unexpected schema version %(version)r, %(expected)s expected.",
                    version=data.get("schema_version"),
                    expected=SCHEMA_VERSION,
                )
            )
        quotes = data.get("quotes")
        if not isinstance(quotes, list):
            raise AIResponseError(_("The answer has no list of documents."))
        if len(quotes) > MAX_QUOTES:
            raise AIResponseError(_("The answer has too many documents."))
        result = {
            "schema_version": SCHEMA_VERSION,
            "quotes": [],
            "unrelated_message_refs": [
                ref
                for ref in self.texts(data.get("unrelated_message_refs"), 20)
                if ref in self.message_labels
            ],
            "notes": self.text(data.get("notes")),
        }
        keys = set()
        for index, quote_data in enumerate(quotes, 1):
            quote = self.quote(quote_data, index)
            if quote["quote_key"] in keys:
                quote["quote_key"] = f"{quote['quote_key']}-{index}"
            keys.add(quote["quote_key"])
            result["quotes"].append(quote)
        return result


def validate_response(
    env,
    data,
    message_labels=(),
    document_labels=(),
    target_references=(),
    document_types=None,
):
    """Check an answer of the AI and return it normalised.

    :param document_types: the document types allowed, ``None`` to accept any.
    :raise AIResponseError: when the answer cannot be used at all.
    """
    validator = _QuoteValidator(
        env, message_labels, document_labels, target_references, document_types
    )
    return validator.response(data)
