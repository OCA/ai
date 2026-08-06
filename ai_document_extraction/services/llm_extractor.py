# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import json
import re
from datetime import date, datetime

import requests

SYSTEM_PROMPT = (
    "/no_think\n"
    "You are a strict invoice data extraction assistant. You will receive an "
    "image of an invoice or receipt. Extract the requested fields from the "
    "image as a single JSON object.\n"
    "- partner_name is the name of the company that issued the invoice (the "
    "supplier for a vendor bill, the customer for a customer invoice). A "
    "short logo or slogan in the document (e.g. 'voslo') MUST NOT be used as "
    "the partner_name; only a full company name with a legal suffix such as "
    "A.Ş., Ltd., GmbH, Inc., S.L. is the issuer. Never use your own model "
    "name as the issuer.\n"
    "- Extract real invoice data only. Do not calculate missing values; "
    "output null if unknown.\n"
    "- invoice_number must be exactly as printed on the document (e.g. "
    "'FT-2023-0042'). It can never be a URL, a file token or a long hex "
    "hash; if it looks like one of those, output null.\n"
    "- invoice_date must be 'YYYY-MM-DD' as printed on the document; null if "
    "not visible.\n"
    "- amount_untaxed is the subtotal (before tax), amount_tax the tax amount, "
    "amount_total the final total. Read them from the document, never compute "
    "them.\n"
    "- description is a short free-text summary of what the invoice is for "
    "(e.g. the service or product category), or null.\n"
    "- lines: each visible line item with its product or service name, "
    "quantity and unit price. tax_rate must be a number matching one of the "
    "provided 'Available tax rates' (e.g. 20 for 20%), or null when the line "
    "has no tax.\n"
    "- currency must be one of the provided 'Available currencies' (ISO code) "
    "or null.\n"
    "Respond ONLY with a valid JSON object."
)

EXPECTED_FIELDS = (
    "partner_name",
    "invoice_number",
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

_HASH_INVOICE_NUMBER = re.compile(r"[0-9a-fA-F]{16,}")


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


def _validate_invoice_number(data):
    candidate = str(data.get("invoice_number") or "").strip()
    if (
        _HASH_INVOICE_NUMBER.fullmatch(candidate)
        or "://" in candidate
        or "%" in candidate
        or "\\" in candidate
    ):
        data["invoice_number"] = None


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
    _validate_invoice_number(data)
    _validate_partner_name(data)
    _validate_invoice_date(data)
    _validate_currency(data, available_currencies)
    _validate_lines(data, available_taxes)
    return data


def extract_invoice_data_from_image(
    image_path,
    api_base_url,
    api_model_name,
    api_key="dummy",
    timeout=120,
    available_taxes=None,
    available_currencies=None,
    num_ctx=None,
):
    """Send the invoice image to a vision LLM and return the extracted dict.

    The request is retried once when the model returns an empty or
    unparseable response (e.g. the context window was exceeded), which is
    usually transient.
    """
    with open(image_path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode()
    url = f"{api_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": api_model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded}"},
                    },
                    {
                        "type": "text",
                        "text": _build_user_prompt(
                            available_taxes, available_currencies
                        ),
                    },
                ],
            },
        ],
        "temperature": 0,
        "stream": False,
    }
    if num_ctx:
        try:
            num_ctx = int(num_ctx)
        except (TypeError, ValueError):
            num_ctx = None
        if num_ctx:
            payload["options"] = {"num_ctx": num_ctx}
    headers = {}
    if api_key and api_key != "dummy":
        headers["Authorization"] = f"Bearer {api_key}"
    last_error = None
    for _attempt in range(2):
        try:
            response = requests.post(
                url, json=payload, headers=headers, timeout=timeout
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not (content or "").strip():
                raise ValueError("The vision model returned an empty response.")
            data = _parse_json_response(content)
            return _validate_data(
                data,
                available_taxes=available_taxes,
                available_currencies=available_currencies,
            )
        except ValueError as error:
            last_error = error
    raise last_error
