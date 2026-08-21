# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from .catalog_schema import GROUP_WEIGHTS, get_attribute_meta

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None

# Keys where larger is better (en az)
AT_LEAST_KEYS = {
    "clean_water_tank_l",
    "dirty_water_tank_l",
    "tank_capacity_l",
    "brush_motor_power_w",
    "vacuum_motor_power_w",
    "motor_power_w",
    "brush_diameter_mm",
    "brush_pressure_kg",
    "brush_speed_rpm",
    "productivity_m2_h",
    "suction_power_w",
    "suction_power",
    "cleaning_area_per_charge_m2",
}

# Keys where smaller is better (en fazla / fazla olmamalı)
AT_MOST_KEYS = {
    "gross_weight_kg",
    "weight_kg",
    "noise_db",
    "noise_level_db",
    "fuel_consumption_kg_h",
    "electricity_consumption_kwh",
}


def _parse_range(value):
    """Parse '250 - 540' or '250-540' into (low, high) or None."""
    if value is None:
        return None
    s = str(value).strip().replace(",", ".")
    m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*[-–]\s*([0-9]+(?:\.[0-9]+)?)\s*$", s)
    if m:
        try:
            return (float(m.group(1)), float(m.group(2)))
        except ValueError:
            return None
    return None


def _extract_number(value):
    """Extract first numeric value from string like '400 Watt' or '67 Desibel'."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip().replace(",", ".")
        # Handle range first
        if _parse_range(s):
            return None
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)", s)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _to_float(value):
    return _extract_number(value)


def _char_match(req_val, prod_val, threshold=85):
    if req_val is None or prod_val is None:
        return False
    r = str(req_val).strip().lower()
    p = str(prod_val).strip().lower()
    if r == p:
        return True
    if r in p or p in r:
        return True
    if fuzz:
        return fuzz.token_sort_ratio(r, p) >= threshold
    return False


def _numeric_match(req_val, prod_val, tolerance=0.10, key=None):
    """Match numeric requirement against product value which may be scalar or range.

    For AT_LEAST_KEYS (en az), prod >= req is considered match even if diff > tolerance.
    For AT_MOST_KEYS (en fazla), prod <= req is considered match.
    """
    if req_val is None or prod_val is None:
        return False
    # Handle string with units -> extract number
    prod_range = _parse_range(prod_val)
    req_num = _to_float(req_val)
    if prod_range and req_num is not None:
        low, high = prod_range
        return low <= req_num <= high
    req_range = _parse_range(req_val)
    prod_num = _to_float(prod_val)
    if req_range and prod_num is not None:
        low, high = req_range
        return low <= prod_num <= high
    if req_range and prod_range:
        r_low, r_high = req_range
        p_low, p_high = prod_range
        return not (r_high < p_low or p_high < r_low)
    if req_num is not None and prod_num is not None:
        if req_num == 0 and prod_num == 0:
            return True
        if req_num == 0:
            return False
        # Directional logic for spec sheets (en az / en fazla)
        if key in AT_LEAST_KEYS:
            # Product should be >= requirement (allow small tolerance below)
            if prod_num >= req_num * 0.95:
                return True
        if key in AT_MOST_KEYS:
            if prod_num <= req_num * 1.05:
                return True
        diff = abs(req_num - prod_num) / abs(req_num)
        return diff <= tolerance
    return _char_match(req_val, prod_val)


def is_match(key, req_val, prod_val):
    """Type-aware comparison for a single key."""
    meta = get_attribute_meta(key)
    typ = meta.get("type", "char") if meta else "char"
    if prod_val is None or prod_val == "" or prod_val is False:
        return False
    # Treat 0 / 0.0 as missing for tank/weight etc. (import artifact)
    if isinstance(prod_val, (int, float)) and prod_val == 0:
        # Check if key is numeric tank/weight - 0 means missing
        if key in AT_LEAST_KEYS or key in AT_MOST_KEYS or typ in ("integer", "float"):
            return False
    if typ == "boolean":
        if isinstance(prod_val, bool):
            p = prod_val
        elif isinstance(prod_val, str):
            p = prod_val.strip().lower() in ("true", "1", "evet", "yes", "var")
        elif isinstance(prod_val, int):
            p = bool(prod_val)
        else:
            p = bool(prod_val)
        r = (
            bool(req_val)
            if isinstance(req_val, bool)
            else str(req_val).lower() in ("true", "1", "evet", "yes", "var")
        )
        return p == r
    if typ in ("integer", "float"):
        return _numeric_match(req_val, prod_val, key=key)
    if typ == "selection":
        return _char_match(req_val, prod_val, threshold=90)
    # char, text, etc. - try numeric directional first if both look numeric
    if _extract_number(req_val) is not None and _extract_number(prod_val) is not None:
        if key in AT_LEAST_KEYS or key in AT_MOST_KEYS:
            return _numeric_match(req_val, prod_val, key=key)
    return _char_match(req_val, prod_val)


def get_product_value(product, key):
    """Read canonical key from product.template (sparse field x_<key> or x_custom_json_attrs)."""
    field_name = f"x_{key}"
    if field_name in product._fields:
        val = product[field_name]
        if val is False or val is None:
            pass
        else:
            if hasattr(val, "name"):
                return val.name if val else None
            # Treat 0 as missing for numeric fields where 0 is not realistic
            if isinstance(val, (int, float)) and val == 0:
                # Keep 0 for now, but is_match will treat as missing
                return val
            return val
    try:
        blob = product.x_custom_json_attrs or {}
        if isinstance(blob, dict) and key in blob:
            return blob[key]
        if isinstance(blob, dict) and field_name in blob:
            return blob[field_name]
    except AttributeError:
        pass
    try:
        if key in product:
            return product[key]
    except Exception:
        pass
    return None


def score_product(requirements, product):
    """Score a single product against requirements dict. Returns match dict.

    Missing keys (prod_val None/0) are now neutral — they don't penalize percent.
    Percent is calculated over matched + mismatched only.
    """
    if not requirements:
        return {
            "match_count": 0,
            "total": 0,
            "percent": 0.0,
            "weighted_percent": 0.0,
            "matched_keys": [],
            "mismatched_keys": [],
            "missing_keys": [],
            "weighted_score": 0.0,
            "weighted_total": 0.0,
        }
    matched = []
    mismatched = []
    missing = []
    weighted_score = 0.0
    weighted_total = 0.0
    for key, req_val in requirements.items():
        meta = get_attribute_meta(key)
        group = meta.get("group", "genel") if meta else "genel"
        weight = GROUP_WEIGHTS.get(group, 1.0)
        prod_val = get_product_value(product, key)
        # Consider 0 as missing for at-least/at-most numeric keys
        is_missing = prod_val is None or prod_val == "" or prod_val is False
        if not is_missing and isinstance(prod_val, (int, float)) and prod_val == 0:
            if key in AT_LEAST_KEYS or key in AT_MOST_KEYS:
                is_missing = True
        if is_missing:
            missing.append(key)
            continue
        # Count only present keys in denominator
        weighted_total += weight
        if is_match(key, req_val, prod_val):
            matched.append(key)
            weighted_score += weight
        else:
            mismatched.append(key)
    total_present = len(matched) + len(mismatched)
    total = len(requirements)
    # Percent over present keys; if all missing, percent 0
    percent = (len(matched) / total_present * 100) if total_present else 0.0
    weighted_percent = (
        (weighted_score / weighted_total * 100) if weighted_total else 0.0
    )
    return {
        "match_count": len(matched),
        "total": total,
        "present_total": total_present,
        "percent": round(percent, 1),
        "weighted_percent": round(weighted_percent, 1),
        "matched_keys": matched,
        "mismatched_keys": mismatched,
        "missing_keys": missing,
        "weighted_score": round(weighted_score, 2),
        "weighted_total": round(weighted_total, 2),
    }


def find_best_matches(requirements, products, limit=10):
    """Score all products and return top N sorted by weighted_percent then percent."""
    scored = []
    for product in products:
        score = score_product(requirements, product)
        scored.append((product, score))
    scored.sort(
        key=lambda x: (x[1]["weighted_percent"], x[1]["percent"], x[1]["match_count"]),
        reverse=True,
    )
    return scored[:limit]
