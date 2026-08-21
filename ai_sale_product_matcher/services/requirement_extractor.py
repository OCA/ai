# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import io
import json
import os

from .catalog_schema import get_attribute_meta, get_schema_prompt_block

SYSTEM_PROMPT = (
    "/no_think\n"
    "You are a product requirement extractor for an industrial cleaning machine catalog. "
    "Extract customer requirements from the provided document image(s) and/or text as a single JSON object. "
    "Use ONLY canonical keys from the provided schema below — never invent new keys. "
    "Normalize units to the key's expected unit: pressure_bar in bar, flow_rate_l_h in L/h, "
    "power in kW or W as per key, dimensions in cm, weight in kg, capacity in L, noise in dB(A). "
    "For example '120 bar' -> pressure_bar: 120, '2.3 kW' -> motor_power_kw: 2.3, 'Monofaze' -> phase: 'Monofaze (M)'. "
    "For boolean features, use true/false. For missing information, OMIT the key — never output null and never hallucinate. "
    "If the document is in Turkish or English, map to the canonical English keys correctly. "
    "If a value is a range like '250 - 540', keep the string '250 - 540'. "
    "CRITICAL: Output ONLY the JSON object with ONLY the keys that have a clear value in the document; DO NOT include keys with null; keep output under 20 keys; no markdown or extra text."
)


def _build_user_prompt(requirement_text=None, env=None):
    # Sector-independent, always English: fetch live PIM keys when env is available
    schema_block = get_schema_prompt_block(env=env)
    extra = ""
    if requirement_text and requirement_text.strip():
        extra = (
            "\nAdditional requirement text provided by user (use it together with the image):\n"
            f"{requirement_text.strip()}\n"
        )
    return (
        "Extract customer requirements as a JSON object using ONLY keys from this schema:\n"
        f"{schema_block}\n"
        f"{extra}"
        'Output format: {"<canonical_key>": <value>, ...} '
        "Include ONLY keys where a requirement is clearly expressed with a value; DO NOT include keys with null, unknown or missing values; DO NOT invent keys; skip irrelevant keys. "
        "Values must respect the type hint (integer, float, boolean, char, selection). "
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


def _validate_requirements(data, env=None):
    """Drop hallucinated keys and coerce types lightly; keep nulls out."""
    valid = {}
    for key, value in list(data.items()):
        if value is None:
            continue
        meta = get_attribute_meta(key, env=env)
        if not meta:
            # Hallucinated key - drop
            continue
        typ = meta.get("type", "char")
        if typ == "boolean":
            if isinstance(value, bool):
                valid[key] = value
            elif isinstance(value, str):
                low = value.strip().lower()
                if low in ("true", "evet", "yes", "1", "var"):
                    valid[key] = True
                elif low in ("false", "hayır", "hayir", "no", "0", "yok"):
                    valid[key] = False
            elif isinstance(value, int):
                valid[key] = bool(value)
        elif typ in ("integer",):
            try:
                if isinstance(value, bool):
                    continue
                if (
                    isinstance(value, str)
                    and "-" in value
                    and value.replace("-", "")
                    .replace(".", "")
                    .replace(" ", "")
                    .isdigit()
                ):
                    # Range string - keep as char-like
                    valid[key] = value.strip()
                else:
                    valid[key] = int(float(str(value).replace(",", ".").strip()))
            except (ValueError, TypeError):
                continue
        elif typ in ("float",):
            try:
                if isinstance(value, bool):
                    continue
                if isinstance(value, str) and "-" in value:
                    # Keep range as string for matching logic
                    cleaned = value.strip()
                    # If it looks like "250 - 540", keep
                    if any(c.isdigit() for c in cleaned):
                        valid[key] = cleaned
                        continue
                valid[key] = float(str(value).replace(",", ".").strip())
            except (ValueError, TypeError):
                continue
        else:
            # char / selection / text
            if isinstance(value, bool):
                valid[key] = str(value)
            else:
                valid[key] = str(value).strip() if str(value).strip() else None
                if valid[key] is None:
                    continue
    return valid


def parse_and_validate(content, env=None):
    data = _parse_json_response(content)
    return _validate_requirements(data, env=env)


def _encode_image(image_path, connection):
    is_ollama = "ollama" in (connection.url or "").lower()
    if is_ollama:
        with open(image_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
        ext = os.path.splitext(image_path)[1].lower()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }.get(ext, "image/png")
    else:
        from PIL import Image

        buf = io.BytesIO()
        with Image.open(image_path) as im:
            im.convert("RGB").save(buf, "JPEG", quality=90)
        encoded = base64.b64encode(buf.getvalue()).decode()
        mime = "image/jpeg"
    return mime, encoded


def build_vision_message(image_path, connection, requirement_text=None, env=None):
    """Build OpenAI-compatible vision message with image + requirement text."""
    mime, encoded = _encode_image(image_path, connection)
    return {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{encoded}"},
            },
            {
                "type": "text",
                "text": _build_user_prompt(requirement_text=requirement_text, env=env),
            },
        ],
    }


def build_vision_message_multi(
    image_paths, connection, requirement_text=None, env=None
):
    """Build a single user message carrying multiple page images (for multi-page PDFs)."""
    content = []
    for path in image_paths:
        mime, encoded = _encode_image(path, connection)
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{encoded}"},
            }
        )
    content.append(
        {
            "type": "text",
            "text": _build_user_prompt(requirement_text=requirement_text, env=env),
        }
    )
    return {"role": "user", "content": content}


def build_text_message(requirement_text, env=None):
    return {
        "role": "user",
        "content": _build_user_prompt(requirement_text=requirement_text, env=env),
    }
