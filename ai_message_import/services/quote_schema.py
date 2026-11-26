# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Contract between the module and the AI: answer schema and instructions.

The text of the instructions is data (``ai.message.import.prompt``): here they are
only assembled. The AI gives each document its type among the types of the
installed modules (purchase, sale...): the prompt of each type describes when a
document is of that type and who its partner is, see ``system_instruction``
and ``response_schema``. Any
change to the answer structure must bump ``SCHEMA_VERSION`` and be reflected in
``quote_validator.py``.
"""

import copy

from .prompts import fill_placeholders

SCHEMA_VERSION = "3.1"

_STRING = {"type": "string"}
_NUMBER = {"type": "number"}
_DATE = {"type": "string", "format": "date"}
_CONFIDENCE = {"type": "number", "minimum": 0, "maximum": 1}
_STRINGS = {"type": "array", "items": _STRING}

LINE_SCHEMA = {
    "type": "object",
    "properties": {
        "product_code": _STRING,
        "own_code": _STRING,
        "barcode": _STRING,
        "description": _STRING,
        "quantity": _NUMBER,
        "uom": _STRING,
        "price_unit": _NUMBER,
        "discount_percent": _NUMBER,
        "subtotal": _NUMBER,
        "tax_percent": _NUMBER,
        "delivery_date": _DATE,
        "is_service": {"type": "boolean"},
        "confidence": _CONFIDENCE,
    },
    "required": ["description", "quantity", "confidence"],
}

QUOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "quote_key": _STRING,
        "document_type": _STRING,
        "relation": {"type": "string", "enum": ["new", "update", "duplicate"]},
        "target_reference": _STRING,
        "relation_reason": _STRING,
        "remove_missing_lines": {"type": "boolean"},
        "message_refs": _STRINGS,
        "document_refs": _STRINGS,
        "partner": {
            "type": "object",
            "properties": {
                "name": _STRING,
                "vat": _STRING,
                "email": _STRING,
                "phone": _STRING,
                "street": _STRING,
                "city": _STRING,
                "zip": _STRING,
                "country_code": _STRING,
                "confidence": _CONFIDENCE,
            },
            "required": ["confidence"],
        },
        "quote_number": _STRING,
        "quote_date": _DATE,
        "currency": _STRING,
        "prices_include_tax": {"type": "boolean"},
        "payment_terms": {
            "type": "object",
            "properties": {
                "text": _STRING,
                "days": {"type": "integer"},
                "end_of_month": {"type": "boolean"},
            },
        },
        "delivery": {
            "type": "object",
            "properties": {
                "date": _DATE,
                "date_text": _STRING,
                "date_is_ambiguous": {"type": "boolean"},
                "address": _STRING,
            },
        },
        "lines": {"type": "array", "items": LINE_SCHEMA},
        "global_discount": {
            "type": "object",
            "properties": {
                "percent": _NUMBER,
                "amount": _NUMBER,
                "description": _STRING,
            },
        },
        "shipping": {
            "type": "object",
            "properties": {"amount": _NUMBER, "description": _STRING},
        },
        "totals": {
            "type": "object",
            "properties": {"untaxed": _NUMBER, "tax": _NUMBER, "total": _NUMBER},
        },
        "clarifications": _STRINGS,
        "warnings": _STRINGS,
        "confidence": _CONFIDENCE,
    },
    "required": [
        "quote_key",
        "document_type",
        "relation",
        "partner",
        "lines",
        "confidence",
    ],
}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "schema_version": {"type": "string", "enum": [SCHEMA_VERSION]},
        "quotes": {"type": "array", "items": QUOTE_SCHEMA},
        "unrelated_message_refs": _STRINGS,
        "notes": _STRING,
    },
    "required": ["schema_version", "quotes"],
}


def system_instruction(template, descriptions):
    """The instructions for the AI.

    :param template: the extraction prompt, with the placeholders ``{types}``
        and ``{version}``.
    :param descriptions: ``{key: description}`` of the installed document
        types: when a document is of that type and who its partner is.
    """
    lines = [
        f'  - "{key}": {" ".join(description.split())}'
        for key, description in descriptions.items()
    ]
    return fill_placeholders(template, types="\n".join(lines), version=SCHEMA_VERSION)


def response_schema(types):
    """The answer schema, with the installed document types."""
    schema = copy.deepcopy(RESPONSE_SCHEMA)
    schema["properties"]["quotes"]["items"]["properties"]["document_type"] = {
        "type": "string",
        "enum": list(types),
    }
    return schema
