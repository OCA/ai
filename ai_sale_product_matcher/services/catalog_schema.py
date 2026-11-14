# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import re

_logger = logging.getLogger(__name__)

GROUP_WEIGHTS = {
    "general": 1.0,
    "technical": 1.5,
    "hardware": 1.2,
    "accessory": 0.7,
}

DEFAULT_ATTRIBUTES = [
    {
        "key": "pressure_bar",
        "label": "Operating Pressure (bar)",
        "type": "float",
        "group": "technical",
    },
    {
        "key": "flow_rate_l_h",
        "label": "Flow Rate (L/h)",
        "type": "float",
        "group": "technical",
    },
    {
        "key": "motor_power_kw",
        "label": "Motor Power (kW)",
        "type": "float",
        "group": "technical",
    },
    {
        "key": "motor_power_w",
        "label": "Motor Power (W)",
        "type": "float",
        "group": "technical",
    },
    {
        "key": "voltage_v",
        "label": "Voltage (V)",
        "type": "integer",
        "group": "technical",
    },
    {
        "key": "phase",
        "label": "Electrical Phase",
        "type": "char",
        "group": "technical",
    },
    {
        "key": "weight_kg",
        "label": "Weight (kg)",
        "type": "float",
        "group": "general",
    },
    {
        "key": "capacity_l",
        "label": "Capacity (L)",
        "type": "float",
        "group": "technical",
    },
    {
        "key": "noise_db",
        "label": "Noise Level (dB)",
        "type": "float",
        "group": "technical",
    },
    {
        "key": "speed_rpm",
        "label": "Speed (RPM)",
        "type": "integer",
        "group": "technical",
    },
    {
        "key": "width_cm",
        "label": "Width (cm)",
        "type": "float",
        "group": "general",
    },
    {
        "key": "height_cm",
        "label": "Height (cm)",
        "type": "float",
        "group": "general",
    },
    {
        "key": "length_cm",
        "label": "Length (cm)",
        "type": "float",
        "group": "general",
    },
    {
        "key": "material",
        "label": "Material",
        "type": "char",
        "group": "hardware",
    },
    {
        "key": "color",
        "label": "Color",
        "type": "char",
        "group": "general",
    },
    {
        "key": "has_detergent_tank",
        "label": "Detergent Tank Included",
        "type": "boolean",
        "group": "accessory",
    },
    {
        "key": "auto_start_stop",
        "label": "Automatic Start/Stop",
        "type": "boolean",
        "group": "hardware",
    },
    {
        "key": "warranty_months",
        "label": "Warranty (Months)",
        "type": "integer",
        "group": "general",
    },
    {
        "key": "description",
        "label": "Description / Application",
        "type": "char",
        "group": "general",
    },
]


def normalize_attr_key(name):
    """Normalize an attribute or field name to a canonical snake_case key."""
    cleaned = (name or "").strip().lower()
    if cleaned.startswith("x_"):
        cleaned = cleaned[2:]
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned).strip("_")
    return cleaned


def get_attributes(env=None):
    """Return catalog attributes, merging live product attributes when env is given."""
    merged = {attr["key"]: dict(attr) for attr in DEFAULT_ATTRIBUTES}
    if env is None:
        return list(merged.values())
    try:
        for pattr in env["product.attribute"].search([]):
            key = normalize_attr_key(pattr.name)
            if not key:
                continue
            values = pattr.value_ids.mapped("name")
            if key not in merged:
                merged[key] = {
                    "key": key,
                    "label": pattr.name,
                    "type": "selection" if values else "char",
                    "group": "technical",
                    "selection_options": values[:10],
                }
            elif values and not merged[key].get("selection_options"):
                merged[key]["selection_options"] = values[:10]
    except Exception:
        _logger.debug("Could not read product.attribute records", exc_info=True)
    return list(merged.values())


def get_schema_prompt_block(env=None):
    """Build compressed prompt block: key | label | type | group."""
    attrs = get_attributes(env=env)
    lines = []
    for attr in attrs:
        key = attr.get("key", "")
        label = attr.get("label") or key
        typ = attr.get("type", "char")
        group = attr.get("group", "general")
        extra = ""
        if typ == "selection" and attr.get("selection_options"):
            opts = ", ".join(attr["selection_options"][:5])
            extra = f" | options: {opts}"
        lines.append(f"- {key}: {label} ({typ}, group={group}){extra}")
    return "\n".join(lines)


def get_attribute_meta(key, env=None):
    """Return attribute metadata dict for key or None."""
    for attr in get_attributes(env=env):
        if attr.get("key") == key:
            return attr
    return None
