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

# Load bundled catalog schema (generated from katalog-sablonu.json)
_CATALOG_SCHEMA = None


def _load_catalog_schema():
    global _CATALOG_SCHEMA
    if _CATALOG_SCHEMA is not None:
        return _CATALOG_SCHEMA
    # Try bundled data file first
    bundle = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "catalog_schema.json"
    )
    # Fallback to workspace file (dev only)
    fallback = "/home/volkan/dev/aktem-makine/katalog-sablonu.json"
    for path in [bundle, fallback]:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                # katalog-sablonu has attributes/groups/sets/products top-level
                if "attributes" in data:
                    _CATALOG_SCHEMA = data
                    return data
                _CATALOG_SCHEMA = data
                return data
    _CATALOG_SCHEMA = {"attributes": [], "groups": [], "sets": []}
    return _CATALOG_SCHEMA


def get_attributes():
    return _load_catalog_schema().get("attributes", [])


def get_groups():
    return _load_catalog_schema().get("groups", [])


def get_sets():
    return _load_catalog_schema().get("sets", [])


def get_schema_prompt_block():
    """Build compressed prompt block: key | label_tr | type | group."""
    attrs = get_attributes()
    lines = []
    for attr in attrs:
        key = attr.get("key", "")
        label = attr.get("label_tr", key)
        typ = attr.get("type", "char")
        group = attr.get("group", "genel")
        # Include select options hint for select types
        extra = ""
        if typ == "selection" and attr.get("selection_options"):
            opts = ", ".join(attr["selection_options"][:5])
            extra = f" | options: {opts}"
        lines.append(f"- {key}: {label} ({typ}, group={group}){extra}")
    return "\n".join(lines)


def get_attribute_meta(key):
    """Return attribute metadata dict for key or None."""
    for attr in get_attributes():
        if attr.get("key") == key:
            return attr
    return None
