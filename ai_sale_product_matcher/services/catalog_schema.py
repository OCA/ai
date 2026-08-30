# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
import os

_logger = logging.getLogger(__name__)

# Groups weighting for scoring - higher weight means more important for matching
GROUP_WEIGHTS = {
    "genel": 1.0,
    "teknik": 1.5,
    "donanim": 1.2,
    "aksesuar": 0.7,
}

# Fallback static schema (for tests / sector-independent demo with cleaning machines)
_CATALOG_SCHEMA = None


def _load_catalog_schema():
    global _CATALOG_SCHEMA
    if _CATALOG_SCHEMA is not None:
        return _CATALOG_SCHEMA
    bundle = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "catalog_schema.json"
    )
    if os.path.exists(bundle):
        with open(bundle, encoding="utf-8") as f:
            _CATALOG_SCHEMA = json.load(f)
        return _CATALOG_SCHEMA
    _CATALOG_SCHEMA = {"attributes": [], "groups": [], "sets": []}
    return _CATALOG_SCHEMA


def get_attributes(env=None):
    """Return catalog attributes; merge live PIM attributes when env is given.

    The bundled JSON schema is the primary source so labels stay stable;
    live PIM keys are merged in when they add new entries.
    """
    file_attrs = _load_catalog_schema().get("attributes", [])
    if env is None:
        return file_attrs
    try:
        live_attrs = env["attribute.attribute"].search([])
        if not live_attrs:
            return file_attrs
        live_keys = set()
        for attr in live_attrs:
            key = (
                attr.field_id.name[2:]
                if attr.field_id and attr.field_id.name.startswith("x_")
                else attr.name
            )
            live_keys.add(key)
        file_keys = set(a.get("key") for a in file_attrs)
        if live_keys == file_keys:
            return file_attrs
        merged = {a["key"]: a for a in file_attrs}
        for attr in live_attrs:
            key = (
                attr.field_id.name[2:]
                if attr.field_id and attr.field_id.name.startswith("x_")
                else attr.name
            )
            if key not in merged:
                merged[key] = {
                    "key": key,
                    "label_tr": attr.field_id.field_description
                    if attr.field_id
                    else attr.name,
                    "label_en": attr.name,
                    "type": attr.attribute_type,
                    "group": "genel",
                }
        return list(merged.values())
    except Exception:
        return file_attrs


def get_groups(env=None):
    if env is not None:
        try:
            groups = env["attribute.group"].search([])
            if groups:
                return [{"name": g.name} for g in groups]
        except Exception:
            _logger.debug("Could not read live attribute groups", exc_info=True)
    return _load_catalog_schema().get("groups", [])


def get_sets(env=None):
    if env is not None:
        try:
            sets = env["attribute.set"].search([])
            if sets:
                return [{"name": s.name} for s in sets]
        except Exception:
            _logger.debug("Could not read live attribute sets", exc_info=True)
    return _load_catalog_schema().get("sets", [])


def get_schema_prompt_block(env=None):
    """Build compressed prompt block: key | label | type | group.

    Always English prompt, sector-independent: keys are PIM attribute keys.
    Labels are Turkish (from PIM) to help LLM map Turkish specs to English keys.
    """
    attrs = get_attributes(env=env)
    lines = []
    for attr in attrs:
        key = attr.get("key", "")
        # Prefer Turkish label for Turkish specs, even though prompt is English
        label = attr.get("label_tr") or attr.get("label_en") or key
        typ = attr.get("type", "char")
        group = attr.get("group", "genel")
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
