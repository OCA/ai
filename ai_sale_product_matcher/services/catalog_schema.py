# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import os

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
    fallback = "/home/volkan/dev/aktem-makine/katalog-sablonu.json"
    for path in [bundle, fallback]:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                if "attributes" in data:
                    _CATALOG_SCHEMA = data
                    return data
                _CATALOG_SCHEMA = data
                return data
    _CATALOG_SCHEMA = {"attributes": [], "groups": [], "sets": []}
    return _CATALOG_SCHEMA


def get_attributes(env=None):
    """Sector-independent: if env provided, fetch live PIM attributes; else fallback to bundled file."""
    if env is not None:
        try:
            # Live PIM: attribute.attribute holds all typed attributes (via attribute_set)
            attrs = env["attribute.attribute"].search([])
            result = []
            for attr in attrs:
                # field_name is like x_pressure_bar -> key is without x_
                key = (
                    attr.field_id.name[2:]
                    if attr.field_id and attr.field_id.name.startswith("x_")
                    else attr.name
                )
                # Map attribute_type to catalog type
                type_map = {
                    "char": "char",
                    "text": "text",
                    "select": "selection",
                    "multiselect": "multiselect",
                    "boolean": "boolean",
                    "integer": "integer",
                    "float": "float",
                    "date": "date",
                    "datetime": "datetime",
                    "binary": "binary",
                    "many2one": "many2one",
                    "many2many": "many2many",
                }
                typ = type_map.get(attr.attribute_type, "char")
                group = (
                    attr.attribute_group_id.name.lower()
                    if attr.attribute_group_id
                    else "genel"
                )
                # Normalize group to our 4 buckets for weighting
                if "teknik" in group:
                    group = "teknik"
                elif "donan" in group:
                    group = "donanim"
                elif "akses" in group:
                    group = "aksesuar"
                else:
                    group = "genel"
                result.append(
                    {
                        "key": key,
                        "label_tr": attr.field_id.field_description
                        if attr.field_id
                        else attr.name,
                        "label_en": attr.name,
                        "type": typ,
                        "group": group,
                    }
                )
            if result:
                return result
        except Exception:
            pass
    return _load_catalog_schema().get("attributes", [])


def get_groups(env=None):
    if env is not None:
        try:
            groups = env["attribute.group"].search([])
            if groups:
                return [{"name": g.name} for g in groups]
        except Exception:
            pass
    return _load_catalog_schema().get("groups", [])


def get_sets(env=None):
    if env is not None:
        try:
            sets = env["attribute.set"].search([])
            if sets:
                return [{"name": s.name} for s in sets]
        except Exception:
            pass
    return _load_catalog_schema().get("sets", [])


def get_schema_prompt_block(env=None):
    """Build compressed prompt block: key | label | type | group.

    Always English prompt, sector-independent: keys are live PIM attribute keys.
    If env is given, fetch live; otherwise fallback to bundled file (for tests).
    """
    attrs = get_attributes(env=env)
    lines = []
    for attr in attrs:
        key = attr.get("key", "")
        label = attr.get("label_en") or attr.get("label_tr") or key
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
