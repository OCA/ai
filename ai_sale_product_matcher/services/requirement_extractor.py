# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from .catalog_schema import get_attribute_meta, get_schema_prompt_block

SYSTEM_PROMPT = (
    "You are a technical product requirement extractor. "
    "Extract customer product requirements from the provided document image(s) "
    "and/or text as a single JSON object. "
    "Use ONLY canonical keys from the provided schema below — never invent new "
    "keys. "
    "Normalize numeric values to the unit indicated by the key or label "
    "(e.g. pressure_bar in bar, flow_rate_l_h in L/h, motor_power_kw in kW, "
    "weight_kg in kg, capacity_l in L, noise_db in dB). "
    "For boolean features, use true or false. For missing information, OMIT the "
    "key — never output null and never hallucinate. "
    "If a value is a numeric range such as '250 - 540', keep the string "
    "'250 - 540'. "
    "CRITICAL: Output ONLY the JSON object with ONLY the keys that have a clear "
    "value in the document; DO NOT include keys with null; keep output under 20 "
    "keys; no markdown or extra text."
)


def _build_user_prompt(requirement_text=None, env=None):
    schema_block = get_schema_prompt_block(env=env)
    extra = ""
    if requirement_text and requirement_text.strip():
        extra = (
            "\nAdditional requirement text provided by user:\n"
            f"{requirement_text.strip()}\n"
        )
    return (
        "Extract customer requirements as a JSON object using ONLY keys from "
        "this schema:\n"
        f"{schema_block}\n"
        f"{extra}"
        'Output format: {"<canonical_key>": <value>, ...} '
        "Include ONLY keys where a requirement is clearly expressed with a "
        "value; DO NOT include keys with null, unknown or missing values; "
        "DO NOT invent keys; skip irrelevant keys. "
        "Values must respect the type hint (integer, float, boolean, char, "
        "selection). "
        "Output ONLY the JSON object, no markdown, max 20 keys."
    )


def _parse_json_response(content):
    decoder = json.JSONDecoder()
    for pos in range(len(content)):
        if content[pos] == "{":
            try:
                data, _ = decoder.raw_decode(content, pos)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                raise ValueError("LLM response is not a JSON object")
            return data
    raise ValueError(f"No JSON object found in LLM response: {content[:500]}")


_DROP = object()
_TRUE_WORDS = ("true", "evet", "yes", "1", "var")
_FALSE_WORDS = ("false", "hayır", "hayir", "no", "0", "yok")


def _is_range_string(value):
    return (
        isinstance(value, str)
        and "-" in value
        and value.replace("-", "").replace(".", "").replace(" ", "").isdigit()
    )


def _coerce_boolean(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in _TRUE_WORDS:
            return True
        if low in _FALSE_WORDS:
            return False
        return _DROP
    if isinstance(value, int):
        return bool(value)
    return _DROP


def _coerce_integer(value):
    if isinstance(value, bool):
        return _DROP
    try:
        if _is_range_string(value):
            return value.strip()
        return int(float(str(value).replace(",", ".").strip()))
    except (ValueError, TypeError):
        return _DROP


def _coerce_float(value):
    if isinstance(value, bool):
        return _DROP
    if isinstance(value, str) and "-" in value:
        cleaned = value.strip()
        if any(c.isdigit() for c in cleaned):
            return cleaned
    try:
        return float(str(value).replace(",", ".").strip())
    except (ValueError, TypeError):
        return _DROP


def _coerce_char(value):
    if isinstance(value, bool):
        return str(value)
    return str(value).strip() if str(value).strip() else None


_COERCERS = {
    "boolean": _coerce_boolean,
    "integer": _coerce_integer,
    "float": _coerce_float,
}


def _validate_requirements(data, env=None):
    """Drop hallucinated keys and coerce types lightly; keep nulls out."""
    valid = {}
    for key, value in data.items():
        if value is None:
            continue
        meta = get_attribute_meta(key, env=env)
        if not meta:
            continue
        coerce = _COERCERS.get(meta.get("type", "char"), _coerce_char)
        result = coerce(value)
        if result is not _DROP and result is not None:
            valid[key] = result
    return valid


def parse_and_validate(content, env=None):
    data = _parse_json_response(content)
    return _validate_requirements(data, env=env)
