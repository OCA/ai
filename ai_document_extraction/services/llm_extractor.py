# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
from datetime import date, datetime

SYSTEM_PROMPT = (
    "/no_think\n"
    "Extract invoice data from the image as a JSON object. "
    "partner_name is the company that issued the invoice (the seller/supplier "
    "for a vendor bill, the customer for a customer invoice); never use a "
    "logo, slogan or model name. "
    "invoice_number: the document's business number exactly as printed - look "
    "for a field labeled Invoice, Receipt, Order or Document number; if "
    "several exist prefer Invoice, then Receipt, then Order/Document; copy it "
    "even when it looks like a long hexadecimal code; never a URL or file "
    "path; null if none of those labels exist. "
    "payment_reference: the payment or transaction reference - a field labeled "
    "Payment number, Transaction ID or Payment ID; null if none. "
    "invoice_date as YYYY-MM-DD when a date is visible on the document, else "
    "null. "
    "amount_untaxed, amount_tax and amount_total read from the document. "
    "lines: each visible line item with name, quantity, price_unit and "
    "tax_rate from the provided tax rates (or null when untaxed). "
    "currency from the provided currency codes (or null). "
    "description: a short summary of what the document is for. "
    "Output ONLY the JSON object."
)

EXPECTED_FIELDS = (
    "partner_name",
    "invoice_number",
    "payment_reference",
    "invoice_date",
    "amount_untaxed",
    "amount_tax",
    "amount_total",
    "currency",
    "description",
    "lines",
)

_MODEL_NAMES = {
    "deepseek",
    "qwen",
    "qwen2",
    "qwen2.5",
    "qwen3",
    "qwen3-vl",
    "llama",
    "llama3",
    "gpt",
    "gpt-4",
    "gpt-4o",
    "claude",
    "gemini",
    "mistral",
    "mixtral",
    "phi",
    "deepseek-v4-flash",
}

_LEGAL_SUFFIXES = (
    "a.ş.",
    "a.s.",
    "ltd.",
    "ltd",
    "gmbh",
    "inc.",
    "s.l.",
    "s.a.",
    "b.v.",
    "sarl",
    "llc",
    "corp.",
    "co.",
)


def _build_user_prompt(available_taxes=None, available_currencies=None):
    tax_block = ""
    if available_taxes:
        tax_lines = "\n".join(
            f"- {tax['name']} = {tax['amount']}%" for tax in available_taxes
        )
        tax_block = (
            "Available tax rates (tax_rate must be one of these numbers):\n"
            f"{tax_lines}\n"
        )
    currency_block = ""
    if available_currencies:
        currency_block = (
            f"Available currencies (ISO codes): {', '.join(available_currencies)}\n"
        )
    return (
        "Extract the following fields from the invoice image as a single JSON "
        "object:\n"
        '{"partner_name": <str or null>, "invoice_number": <str or null>, '
        '"payment_reference": <str or null>, '
        '"invoice_date": <"YYYY-MM-DD" or null>, "amount_untaxed": <number or null>, '
        '"amount_tax": <number or null>, "amount_total": <number or null>, '
        '"currency": <ISO code or null>, "description": <str or null>, '
        '"lines": [{"name": <str>, "quantity": <number or null>, '
        '"price_unit": <number or null>, "tax_rate": <number or null>}]}\n'
        f"{tax_block}"
        f"{currency_block}"
        "Output ONLY the JSON object, with no markdown or extra text."
    )


def _parse_json_response(content):
    decoder = json.JSONDecoder()
    # Find the first valid JSON object, ignoring leading/trailing noise (e.g.
    # "Sure! Here is the JSON:" or trailing prose with extra braces).
    for position in range(len(content)):
        if content[position] == "{":
            try:
                data, _ = decoder.raw_decode(content, position)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                raise ValueError("LLM response is not a JSON object")
            for field in EXPECTED_FIELDS:
                data.setdefault(field, None)
            if not isinstance(data.get("lines"), list):
                data["lines"] = []
            return data
    raise ValueError(f"No JSON object found in LLM response: {content[:200]}")


def _validate_reference(data, field):
    """Drop a reference that is empty or looks like a URL/path, not a printed number.

    Real receipt numbers can legitimately be long hex codes, so we no longer
    reject hashes; we only reject clearly non-business strings.
    """
    candidate = str(data.get(field) or "").strip()
    if not candidate or "://" in candidate or "%" in candidate or "\\" in candidate:
        data[field] = None


def _validate_partner_name(data):
    candidate = str(data.get("partner_name") or "").strip()
    if candidate.lower() in _MODEL_NAMES or (
        " " not in candidate
        and not any(candidate.lower().endswith(s) for s in _LEGAL_SUFFIXES)
    ):
        data["partner_name"] = None


def _validate_invoice_date(data):
    raw = data.get("invoice_date")
    if not raw:
        return
    try:
        parsed = datetime.strptime(str(raw), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        data["invoice_date"] = None
        return
    if not (date(2000, 1, 1) <= parsed <= date.today()):
        data["invoice_date"] = None


def _validate_currency(data, available_currencies):
    currency = data.get("currency")
    if currency and available_currencies:
        known = {code.strip().upper() for code in available_currencies}
        if str(currency).strip().upper() not in known:
            data["currency"] = None


def _validate_lines(data, available_taxes):
    if not available_taxes:
        return
    available_ids = {int(tax["id"]) for tax in available_taxes}
    available_rates = {
        float(tax["amount"])
        for tax in available_taxes
        if tax.get("amount_type") == "percent"
    }
    for line in data.get("lines") or []:
        if not isinstance(line, dict):
            continue
        tax_id = line.get("tax_id")
        if tax_id is not None:
            try:
                valid = int(tax_id) in available_ids
            except (ValueError, TypeError):
                valid = False
            if not valid:
                line.pop("tax_id", None)
        tax_rate = line.get("tax_rate")
        if tax_rate is not None:
            try:
                valid = float(tax_rate) in available_rates
            except (ValueError, TypeError):
                valid = False
            if not valid:
                line.pop("tax_rate", None)


def _validate_data(data, available_taxes=None, available_currencies=None):
    """Drop hallucinated values so only trustworthy fields reach the move."""
    _validate_reference(data, "invoice_number")
    _validate_reference(data, "payment_reference")
    _validate_partner_name(data)
    _validate_invoice_date(data)
    _validate_currency(data, available_currencies)
    _validate_lines(data, available_taxes)
    return data


def parse_and_validate(content, available_taxes=None, available_currencies=None):
    """Parse raw LLM output into a validated extraction dict."""
    data = _parse_json_response(content)
    return _validate_data(
        data,
        available_taxes=available_taxes,
        available_currencies=available_currencies,
    )
