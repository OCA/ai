# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Small helpers shared by the models and the services of the module.

The ones common to every processor of the received messages come from
``mail_message_import``.
"""

import re
import unicodedata

from odoo.addons.mail_message_import.services.tools import (  # noqa: F401
    AUTOMATION_CONTEXT_KEY,
    automation_user,
    clean_text,
    commit_progress,
    truncate,
)

# Context key: a person changes a document that must not be applied again yet.
NO_AUTO_APPLY_KEY = "ai_message_import_no_auto_apply"

# Legal forms ignored when two company names are compared.
LEGAL_FORMS = {
    "sl",
    "slu",
    "sll",
    "sa",
    "sau",
    "sc",
    "scp",
    "cb",
    "slne",
    "ltd",
    "llc",
    "inc",
    "gmbh",
    "sarl",
    "srl",
    "spa",
    "bv",
    "nv",
    "co",
    "corp",
}


def note_author(env):
    """Partner that signs the notes posted by the module: its agent, or
    OdooBot."""
    agent = env["mail.message.import.config"]._agent_user()
    return agent.partner_id if agent else env.ref("base.partner_root")


def strip_accents(text):
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )


def normalize_text(value):
    """Lowercase words without accents nor punctuation, to compare names."""
    value = strip_accents(clean_text(value)).lower()
    return " ".join(re.findall(r"[a-z0-9]+", value))


def normalize_company_name(value):
    words = normalize_text(value.replace(".", "") if value else "").split()
    return " ".join(word for word in words if word not in LEGAL_FORMS)


def normalize_code(value):
    """Product references compared without case, spaces, dots nor dashes."""
    return re.sub(r"[^a-z0-9]", "", strip_accents(clean_text(value)).lower())


def normalize_vat(value):
    return re.sub(r"[^A-Z0-9]", "", strip_accents(clean_text(value)).upper())


def vat_variants(value):
    """The VAT number, with and without a leading country code."""
    vat = normalize_vat(value)
    variants = {vat} if vat else set()
    if len(vat) > 4 and vat[:2].isalpha():
        variants.add(vat[2:])
    return variants


def same_vat(first, second):
    """Whether two VAT numbers are equal, ignoring their country prefix."""
    first, second = normalize_vat(first), normalize_vat(second)
    if not first or not second:
        return False
    return (
        first == second
        or (first[:2].isalpha() and first[2:] == second)
        or (second[:2].isalpha() and second[2:] == first)
    )
