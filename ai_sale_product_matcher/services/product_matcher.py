# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from .catalog_schema import GROUP_WEIGHTS, get_attribute_meta

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None


def _parse_range(value):
    """Parse '250 - 540' or '250-540' into (low, high) or None."""
    if value is None:
        return None
    s = str(value).strip().replace(",", ".")
    # Match "250 - 540" or "250-540" or "250 – 540"
    m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*[-–]\s*([0-9]+(?:\.[0-9]+)?)\s*$", s)
    if m:
        try:
            return (float(m.group(1)), float(m.group(2)))
        except ValueError:
            return None
    return None


def _to_float(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip().replace(",", ".")
        # If it's a range, return None - range needs special handling
        if _parse_range(s):
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


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


def _numeric_match(req_val, prod_val, tolerance=0.10):
    """Match numeric requirement against product value which may be scalar or range."""
    if req_val is None or prod_val is None:
        return False
    # Product range handling
    prod_range = _parse_range(prod_val)
    req_num = _to_float(req_val)
    if prod_range and req_num is not None:
        low, high = prod_range
        return low <= req_num <= high
    # Requirement is range, product is scalar
    req_range = _parse_range(req_val)
    prod_num = _to_float(prod_val)
    if req_range and prod_num is not None:
        low, high = req_range
        return low <= prod_num <= high
    # Both ranges - overlap?
    if req_range and prod_range:
        r_low, r_high = req_range
        p_low, p_high = prod_range
        return not (r_high < p_low or p_high < r_low)
    # Both scalars - tolerance
    if req_num is not None and prod_num is not None:
        if req_num == 0 and prod_num == 0:
            return True
        if req_num == 0:
            return False
        diff = abs(req_num - prod_num) / abs(req_num)
        return diff <= tolerance
    # Fallback to char match for string numerics
    return _char_match(req_val, prod_val)


def is_match(key, req_val, prod_val):
    """Type-aware comparison for a single key."""
    meta = get_attribute_meta(key)
    typ = meta.get("type", "char") if meta else "char"
    if prod_val is None or prod_val == "":
        return False
    if typ == "boolean":
        # Normalize prod_val
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
        return _numeric_match(req_val, prod_val)
    if typ == "selection":
        return _char_match(req_val, prod_val, threshold=90)
    # char, text, etc.
    return _char_match(req_val, prod_val)


def get_product_value(product, key):
    """Read canonical key from product.template (sparse field x_<key> or x_custom_json_attrs)."""
    field_name = f"x_{key}"
    # Try sparse field
    if field_name in product._fields:
        val = product[field_name]
        # Handle many2one / selection / etc.
        if val is False or val is None:
            # Fallback to JSON
            pass
        else:
            # For attribute.option m2o, return display name
            if hasattr(val, "name"):
                return val.name if val else None
            return val
    # Fallback to JSON blob (if using serialized storage)
    try:
        blob = product.x_custom_json_attrs or {}
        if isinstance(blob, dict) and key in blob:
            return blob[key]
        # Some setups store under field_name
        if isinstance(blob, dict) and field_name in blob:
            return blob[field_name]
    except AttributeError:
        pass
    # Try product.product variant or template fallback via read
    try:
        if key in product:
            return product[key]
    except Exception:
        pass
    return None


def score_product(requirements, product):
    """Score a single product against requirements dict. Returns match dict."""
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
        weighted_total += weight
        prod_val = get_product_value(product, key)
        if prod_val is None or prod_val == "" or prod_val is False:
            missing.append(key)
            continue
        if is_match(key, req_val, prod_val):
            matched.append(key)
            weighted_score += weight
        else:
            mismatched.append(key)
    total = len(requirements)
    match_count = len(matched)
    percent = (match_count / total * 100) if total else 0.0
    weighted_percent = (
        (weighted_score / weighted_total * 100) if weighted_total else 0.0
    )
    return {
        "match_count": match_count,
        "total": total,
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
