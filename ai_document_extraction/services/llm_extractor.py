# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import re
from datetime import date, datetime

import requests

SYSTEM_PROMPT = (
    "You are a strict invoice data extraction assistant. You will receive OCR "
    "text tagged with positional layouts ([HEADER], [BODY], [FOOTER]).\n"
    "- The partner_name is the name of the company that issued the invoice "
    "(the supplier for a vendor bill, the customer for a customer invoice). It "
    "is usually written in the [HEADER] next to the word 'From', 'Supplier', "
    "'Billed by', 'Issuer' or at the top of the document. A short standalone "
    "text in [HEADER] that is just a logo or slogan (e.g. 'voslo') MUST NOT be "
    "used as the partner_name; but a full company name with a legal suffix "
    "such as A.Ş., Ltd., GmbH, Inc., S.L. IS the issuer and must be extracted. "
    "Never use your own model name (e.g. DeepSeek, qwen, GPT) as the issuer.\n"
    "- Extract real invoice data only. Do not calculate missing values; output "
    "null if unknown.\n"
    "- invoice_number must be exactly as printed on the document (e.g. "
    "'FT-2023-0042'). It can never be a URL, a file token or a long hex "
    "hash; if it looks like one of those, output null.\n"
    "- amount_untaxed is the subtotal (before tax), amount_tax the tax amount, "
    "amount_total the final total. Read them from the document, never compute "
    "them.\n"
    "- description is a short free-text summary of what the invoice is for "
    "(e.g. the service or product category), or null.\n"
    "- Extract the invoice line items listed in the [BODY] (product or service "
    "name, quantity and unit price when visible). For each line pick the tax "
    "from the provided 'Available taxes' list using its numeric id, or null "
    "if no exact tax applies. If no line items are visible, output an empty "
    "array.\n"
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


def _build_user_prompt(processed_text, available_taxes=None, available_currencies=None):
    tax_block = ""
    if available_taxes:
        tax_lines = "\n".join(
            f"- {tax['id']}: {tax['name']} ({tax['amount']}%)"
            for tax in available_taxes
        )
        tax_block = f"Available taxes (choose tax_id from this list):\n{tax_lines}\n"
    currency_block = ""
    if available_currencies:
        currency_block = (
            f"Available currencies (ISO codes): {', '.join(available_currencies)}\n"
        )
    return (
        "/no_think\n"
        "Extract the following fields from the OCR text as a single JSON object:\n"
        '{"partner_name": <str or null>, "invoice_number": <str or null>, '
        '"invoice_date": <"YYYY-MM-DD" or null>, "amount_untaxed": <number or null>, '
        '"amount_tax": <number or null>, "amount_total": <number or null>, '
        '"currency": <ISO code or null>, "description": <str or null>, '
        '"lines": [{"name": <str>, "quantity": <number or null>, '
        '"price_unit": <number or null>, '
        '"tax_id": <int from the tax list or null>}]}\n'
        f"{tax_block}"
        f"{currency_block}"
        "Output ONLY the JSON object, with no markdown or extra text.\n\n"
        f"OCR text:\n{processed_text}"
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


def _validate_lines(data, available_tax_ids):
    if not available_tax_ids:
        return
    for line in data.get("lines") or []:
        if not isinstance(line, dict):
            continue
        tax_id = line.get("tax_id")
        if tax_id is None:
            continue
        try:
            valid = int(tax_id) in available_tax_ids
        except (ValueError, TypeError):
            valid = False
        if not valid:
            line.pop("tax_id", None)


def _validate_data(data, available_tax_ids=None, available_currencies=None):
    """Drop hallucinated values so only trustworthy fields reach the move."""
    _validate_invoice_number(data)
    _validate_partner_name(data)
    _validate_invoice_date(data)
    _validate_currency(data, available_currencies)
    _validate_lines(data, available_tax_ids)
    return data


def extract_invoice_data(
    processed_text,
    api_base_url,
    api_model_name,
    api_key="dummy",
    timeout=120,
    available_taxes=None,
    available_currencies=None,
):
    """Call an OpenAI-compatible /chat/completions endpoint and return the dict."""
    url = f"{api_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": api_model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_user_prompt(
                    processed_text, available_taxes, available_currencies
                ),
            },
        ],
        "temperature": 0,
        "stream": False,
    }
    headers = {}
    if api_key and api_key != "dummy":
        headers["Authorization"] = f"Bearer {api_key}"
    response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    data = _parse_json_response(content)
    tax_ids = {int(tax["id"]) for tax in (available_taxes or [])}
    return _validate_data(
        data, available_tax_ids=tax_ids, available_currencies=available_currencies
    )
