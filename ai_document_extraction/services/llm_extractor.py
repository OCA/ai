# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

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
    "such as A.Ş., Ltd., GmbH, Inc., S.L. IS the issuer and must be extracted.\n"
    "- Extract real invoice data only. Do not calculate missing values; output "
    "null if unknown.\n"
    "- amount_untaxed is the subtotal (before tax), amount_tax the tax amount, "
    "amount_total the final total. Read them from the document, never compute "
    "them.\n"
    "- Extract the invoice line items listed in the [BODY] (product or service "
    "name, quantity and unit price when visible). If no line items are visible, "
    "output an empty array.\n"
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
    "lines",
)


def _build_user_prompt(processed_text):
    return (
        "/no_think\n"
        "Extract the following fields from the OCR text as a single JSON object:\n"
        '{"partner_name": <str or null>, "invoice_number": <str or null>, '
        '"invoice_date": <"YYYY-MM-DD" or null>, "amount_untaxed": <number or null>, '
        '"amount_tax": <number or null>, "amount_total": <number or null>, '
        '"currency": <str or null>, '
        '"lines": [{"name": <str>, "quantity": <number or null>, '
        '"price_unit": <number or null>} or null]}\n'
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


def extract_invoice_data(
    processed_text, api_base_url, api_model_name, api_key="dummy", timeout=120
):
    """Call an OpenAI-compatible /chat/completions endpoint and return the dict."""
    url = f"{api_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": api_model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(processed_text)},
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
    return _parse_json_response(content)
