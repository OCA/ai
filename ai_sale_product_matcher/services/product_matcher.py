# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import re

from rapidfuzz import fuzz

from .catalog_schema import GROUP_WEIGHTS, get_attribute_meta, normalize_attr_key

_logger = logging.getLogger(__name__)

AT_LEAST_KEYS = {
    "pressure_bar",
    "flow_rate_l_h",
    "motor_power_kw",
    "motor_power_w",
    "capacity_l",
    "speed_rpm",
    "warranty_months",
}

AT_MOST_KEYS = {
    "weight_kg",
    "noise_db",
}


def _parse_range(value):
    """Parse '250 - 540' or '250-540' into (low, high) or None."""
    if value is None:
        return None
    s = str(value).strip().replace(",", ".")
    m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*[-–]\s*([0-9]+(?:\.[0-9]+)?)\s*$", s)
    if m:
        return (float(m.group(1)), float(m.group(2)))
    return None


def _extract_number(value):
    """Extract first numeric value from string like '400 W' or '67 dB'."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip().replace(",", ".")
        if _parse_range(s):
            return None
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)", s)
        if m:
            return float(m.group(1))
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
    return fuzz.token_sort_ratio(r, p) >= threshold


def _numeric_match(req_val, prod_val, tolerance=0.10, key=None):
    """Match numeric requirement against product value which may be scalar or range."""
    if req_val is None or prod_val is None:
        return False
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
        if key in AT_LEAST_KEYS and prod_num >= req_num * 0.95:
            return True
        if key in AT_MOST_KEYS and prod_num <= req_num * 1.05:
            return True
        diff = abs(req_num - prod_num) / abs(req_num)
        return diff <= tolerance
    return _char_match(req_val, prod_val)


def is_match(key, req_val, prod_val, env=None):
    """Type-aware comparison for a single key."""
    meta = get_attribute_meta(key, env=env)
    typ = meta.get("type", "char") if meta else "char"
    if prod_val is None or prod_val == "" or prod_val is False:
        return False
    if isinstance(prod_val, (int, float)) and prod_val == 0:
        if key in AT_LEAST_KEYS or key in AT_MOST_KEYS or typ in ("integer", "float"):
            return False
    if typ == "boolean":
        if isinstance(prod_val, bool):
            p = prod_val
        elif isinstance(prod_val, str):
            p = prod_val.strip().lower() in ("true", "1", "yes", "evet", "var")
        else:
            p = bool(prod_val)
        r = (
            req_val
            if isinstance(req_val, bool)
            else str(req_val).strip().lower() in ("true", "1", "yes", "evet", "var")
        )
        return p == r
    if typ in ("integer", "float"):
        return _numeric_match(req_val, prod_val, key=key)
    if typ == "selection":
        return _char_match(req_val, prod_val, threshold=90)
    return _char_match(req_val, prod_val)


def get_product_value(product, key):
    """Read canonical key from product attributes, x_<key>, or standard fields."""
    if "attribute_line_ids" in product._fields:
        for line in product.attribute_line_ids:
            attr_key = normalize_attr_key(line.attribute_id.name)
            if attr_key == key:
                names = line.value_ids.mapped("name")
                if names:
                    return ", ".join(names)
    if key == "weight_kg" and "weight" in product._fields and product.weight:
        return product.weight
    for candidate in (f"x_{key}", key):
        if candidate in product._fields:
            val = product[candidate]
            if val not in (False, None):
                if hasattr(val, "name"):
                    return val.name if val else None
                return val
    return None


def score_product(requirements, product, env=None):
    """Score a single product against requirements dict."""
    if not requirements:
        return {
            "match_count": 0,
            "total": 0,
            "present_total": 0,
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
        meta = get_attribute_meta(key, env=env)
        group = meta.get("group", "general") if meta else "general"
        weight = GROUP_WEIGHTS.get(group, 1.0)
        prod_val = get_product_value(product, key)
        is_missing = prod_val is None or prod_val == "" or prod_val is False
        if not is_missing and isinstance(prod_val, (int, float)) and prod_val == 0:
            if key in AT_LEAST_KEYS or key in AT_MOST_KEYS:
                is_missing = True
        if is_missing:
            missing.append(key)
            continue
        weighted_total += weight
        if is_match(key, req_val, prod_val, env=env):
            matched.append(key)
            weighted_score += weight
        else:
            mismatched.append(key)
    total_present = len(matched) + len(mismatched)
    total = len(requirements)
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


def find_best_matches(requirements, products, limit=10, env=None):
    """Score all products and return top N."""
    scored = []
    for product in products:
        score = score_product(requirements, product, env=env)
        scored.append((product, score))
    scored.sort(
        key=lambda x: (
            x[1]["match_count"],
            x[1]["weighted_percent"],
            x[1]["percent"],
        ),
        reverse=True,
    )
    return scored[:limit]
