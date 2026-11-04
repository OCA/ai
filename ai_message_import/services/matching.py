# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Find the Odoo records named by a quote: partner, products, units, terms...

Only exact and unambiguous correspondences are accepted. When several records
fit, nothing is chosen and the candidates are returned for a person to decide.
"""

import re
from dataclasses import dataclass, field

from odoo import _
from odoo.exceptions import ValidationError
from odoo.osv.expression import OR as Domain_or
from odoo.tools import float_compare

from .tools import (
    normalize_code,
    normalize_company_name,
    normalize_text,
    same_vat,
    vat_variants,
)

# Words used for the units of measure, by xml id of the unit.
UOM_ALIASES = {
    "uom.product_uom_unit": [
        "u",
        "ud",
        "uds",
        "un",
        "und",
        "unid",
        "unidad",
        "unidades",
        "unit",
        "units",
        "pc",
        "pcs",
        "pz",
        "pza",
        "pzas",
        "pieza",
        "piezas",
        "ea",
        "each",
    ],
    "uom.product_uom_dozen": ["docena", "docenas", "dozen", "dozens", "dz"],
    "uom.product_uom_kgm": ["kg", "kgs", "kilo", "kilos", "kilogramo", "kilogramos"],
    "uom.product_uom_gram": ["g", "gr", "grs", "gramo", "gramos", "gram", "grams"],
    "uom.product_uom_ton": ["t", "tn", "tonelada", "toneladas", "ton", "tons"],
    "uom.product_uom_litre": [
        "l",
        "lt",
        "lts",
        "litro",
        "litros",
        "liter",
        "liters",
        "litre",
        "litres",
    ],
    "uom.product_uom_meter": ["m", "mt", "mts", "metro", "metros", "meter", "meters"],
    "uom.product_uom_cm": ["cm", "centimetro", "centimetros"],
    "uom.product_uom_km": ["km", "kilometro", "kilometros"],
    "uom.product_uom_hour": ["h", "hr", "hrs", "hora", "horas", "hour", "hours"],
    "uom.product_uom_day": ["dia", "dias", "day", "days"],
}


def escape_like(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# Letters that may carry an accent, a cedilla or a tilde in a name.
ACCENTABLE = re.compile(r"[aceinou]")


def accent_like(word):
    """An ``ilike`` pattern of a normalized ``word`` that also finds it written
    with accents ("porcelanico" finds "Porcelánico"): those letters match any
    character. The candidates must then be compared normalized."""
    return ACCENTABLE.sub("_", word)


def search_langs(env):
    """Languages in which the names of units and terms are compared."""
    installed = {code for code, _name in env["res.lang"].get_installed()}
    return installed | {env.lang or "en_US"}


# Abbreviations of the packagings in short orders.
PACKAGING_WORDS = {
    "c": "caja",
    "cj": "caja",
    "cja": "caja",
    "cjs": "caja",
    "pq": "paquete",
    "paq": "paquete",
    "pal": "palet",
    "plt": "palet",
}


def singular(word):
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


# Plural written in brackets, as in "Hora(s)" or "Unidad(es)".
BRACKET_PLURAL = re.compile(r"\((e?s)\)", re.IGNORECASE)


@dataclass
class Match:
    record: object
    method: str = ""
    candidates: object = None
    notes: list = field(default_factory=list)

    @property
    def ambiguous(self):
        return (
            not self.record and self.candidates is not None and len(self.candidates) > 1
        )


class PartnerMatcher:
    """Find the partner of a quote (its vendor or its customer) among the
    partners of the company.

    :param rank_field: ``supplier_rank`` or ``customer_rank``, used to prefer
        the partners already used in that role and set on the created ones.
    """

    # Trade name of the Spanish localisation (l10n_es_partner): customers and
    # vendors usually go by it ("FRUVEICOD" for "Javier Domínguez Pimentel").
    trade_name_field = "comercial"

    def __init__(self, env, company, sender, rank_field="supplier_rank"):
        self.env = env
        self.company = company
        self.sender = sender
        self.rank_field = rank_field
        Partner = env["res.partner"]
        # The side of the sender is never the partner: the sender and the
        # companies of the database.
        self.excluded = (
            sender.partner_id.commercial_partner_id
            | env["res.company"].sudo().search([]).partner_id
        )
        self.Partner = Partner

    def _domain(self):
        return [("company_id", "in", [False, self.company.id])]

    def _name_fields(self):
        fields = ["name"]
        if self.trade_name_field in self.Partner._fields:
            fields.append(self.trade_name_field)
        return fields

    def _names(self, partner):
        """The normalized names ``partner`` goes by."""
        return {normalize_company_name(partner[f]) for f in self._name_fields()} - {""}

    def _candidates(self, values):
        steps = []
        vat = values.get("vat")
        variants = [v for v in vat_variants(vat) if len(v) >= 5]
        if variants:
            domain = Domain_or([[("vat", "ilike", escape_like(v))] for v in variants])
            found = self.Partner.search(self._domain() + domain, limit=50)
            steps.append(("vat", found.filtered(lambda p: same_vat(p.vat, vat))))
        email = (values.get("email") or "").strip().lower()
        if "@" in email:
            steps.append(
                (
                    "email",
                    self.Partner.search(
                        self._domain() + [("email", "=ilike", escape_like(email))],
                        limit=50,
                    ),
                )
            )
        name = normalize_company_name(values.get("name"))
        if name:
            # The name a person already chose a partner for.
            mappings = self.env["ai.message.import.partner.mapping"].search(
                [("sender_id", "=", self.sender.id), ("key", "=", name)], limit=1
            )
            steps.append(
                (
                    "mapping",
                    mappings.partner_id.filtered(
                        lambda p: p.active
                        and (not p.company_id or p.company_id == self.company)
                    ),
                )
            )
            # A customer or vendor code: the internal reference of the contact.
            code = normalize_code(values.get("name"))
            if code:
                # Its characters in order, whatever the separators.
                found = self.Partner.search(
                    self._domain() + [("ref", "ilike", "%".join(code))], limit=500
                )
                steps.append(
                    ("ref", found.filtered(lambda p: normalize_code(p.ref) == code))
                )
            longest = max(name.split(), key=len)
            domain = Domain_or(
                [[(f, "ilike", accent_like(longest))] for f in self._name_fields()]
            )
            found = self.Partner.search(self._domain() + domain, limit=500)
            # The same name, also written with or without spaces ("Gusto pizza"
            # for "GUSTOPIZZA").
            joined = name.replace(" ", "")
            steps.append(
                (
                    "name",
                    found.filtered(
                        lambda p: joined in {n.replace(" ", "") for n in self._names(p)}
                    ),
                )
            )
            # Its words inside a longer name ("Samoga" for "Cafetería Samoga").
            steps.append(
                (
                    "name_part",
                    found.filtered(
                        lambda p: any(f" {name} " in f" {n} " for n in self._names(p))
                    ),
                )
            )
        return steps

    def match(self, values):
        """:return: a ``Match``; ``method`` is ``"own"`` when the data of the
        quote points to the sender or to a company of the database."""
        own = False
        vat = values.get("vat")
        for method, found in self._candidates(values):
            partners = found.commercial_partner_id
            if partners & self.excluded:
                own = True
            partners -= self.excluded
            if vat:
                # Same name or email, but another VAT number: another company.
                partners = partners.filtered(
                    lambda p: not p.vat or same_vat(p.vat, vat)
                )
            if len(partners) == 1:
                return Match(partners, method, partners)
            if len(partners) > 1:
                ranked = partners.filtered(lambda p: p[self.rank_field] > 0)
                # A part of the name does not choose among several partners.
                if len(ranked) == 1 and method != "name_part":
                    return Match(ranked, method, partners)
                return Match(self.Partner, "ambiguous", partners)
        return Match(self.Partner, "own" if own else "", self.Partner)

    def is_own_name(self, values):
        name = normalize_company_name(values.get("name"))
        return bool(name) and any(name in self._names(p) for p in self.excluded)

    def create_blocker(self, values, min_confidence):
        """Why the partner of the document cannot be created: ``"name"``,
        ``"own"``, ``"confidence"`` or ``"data"``; empty when it can."""
        if not values.get("name"):
            return "name"
        if self.is_own_name(values):
            return "own"
        if values.get("confidence", 0.0) < min_confidence:
            return "confidence"
        if not any(values.get(key) for key in ("vat", "email", "phone", "street")):
            return "data"
        return ""

    def can_create(self, values, min_confidence):
        return not self.create_blocker(values, min_confidence)

    def create_partner(self, values):
        """Create the partner, without its VAT number when Odoo rejects it.

        :return: ``(partner, note)``
        """
        country = self.env["res.country"]
        if values.get("country_code"):
            country = country.search([("code", "=", values["country_code"])], limit=1)
        vals = {
            "name": values["name"],
            "is_company": True,
            self.rank_field: 1,
            "company_id": self.company.id,
            "email": values.get("email") or False,
            "phone": values.get("phone") or False,
            "street": values.get("street") or False,
            "city": values.get("city") or False,
            "zip": values.get("zip") or False,
            "country_id": country.id,
        }
        if values.get("vat"):
            try:
                with self.env.cr.savepoint():
                    return self.Partner.create(dict(vals, vat=values["vat"])), ""
            except ValidationError:
                # The VAT check of the localisation refused the number.
                note = _(
                    "The VAT number %(vat)s was refused by Odoo and was not set.",
                    vat=values["vat"],
                )
                return self.Partner.create(vals), note
        return self.Partner.create(vals), ""


class ProductMatcher:
    """Find the product of a quoted line.

    The equivalences learned from the corrections of the users are searched
    first, and only those of the same sender and the same partner.

    :param ok_field: ``purchase_ok`` or ``sale_ok``, the products that can be
        used on the orders of the document type.
    :param supplier_steps: also search the references and names of the vendor
        price lists of the partner (documents of vendors).
    """

    def __init__(
        self, env, company, sender, partner, ok_field="purchase_ok", supplier_steps=True
    ):
        self.env = env
        self.company = company
        self.sender = sender
        self.partner = partner.commercial_partner_id
        self.ok_field = ok_field
        self.supplier_steps = supplier_steps
        self.Product = env["product.product"]

    def _product_domain(self):
        return [
            (self.ok_field, "=", True),
            ("company_id", "in", [False, self.company.id]),
        ]

    def _usable(self, products):
        return products.filtered(
            lambda p: (
                p.active
                and p[self.ok_field]
                and p.company_id in (self.company, self.env["res.company"])
            )
        )

    def _supplier_products(self, domain, name_key=None):
        infos = self.env["product.supplierinfo"].search(
            [
                ("partner_id", "child_of", self.partner.id),
                ("company_id", "in", [False, self.company.id]),
            ]
            + domain
        )
        if name_key:
            infos = infos.filtered(lambda i: normalize_text(i.product_name) == name_key)
        products = infos.product_id
        for info in infos.filtered(lambda i: not i.product_id):
            products |= info.product_tmpl_id.product_variant_ids
        return self._usable(products)

    def learned_mapping(self, line):
        Mapping = self.env["ai.message.import.product.mapping"]
        if not self.partner:
            # Learned for a partner: unknown yet.
            return Mapping
        for key_type, key in (
            ("code", normalize_code(line.get("product_code"))),
            ("description", normalize_text(line.get("description"))),
        ):
            if not key:
                continue
            mapping = Mapping.search(
                [
                    ("sender_id", "=", self.sender.id),
                    ("partner_id", "=", self.partner.id),
                    ("key_type", "=", key_type),
                    ("key", "=", key),
                ],
                limit=1,
            )
            if mapping and self._usable(mapping.product_id):
                return mapping
        return Mapping

    def match(self, line):
        mapping = self.learned_mapping(line)
        if mapping:
            return Match(mapping.product_id, "mapping", mapping.product_id)
        for method, products in self._search_steps(line):
            products = products()
            if len(products) == 1:
                return Match(products, method, products)
            if len(products) > 1:
                return Match(self.Product, "ambiguous", products)
        return Match(self.Product, "", self.Product)

    def _search_steps(self, line):
        """``(method, search)`` pairs, from the most to the least reliable."""
        code = (line.get("product_code") or "").strip()
        own_code = (line.get("own_code") or "").strip()
        barcode = (line.get("barcode") or "").strip()
        description = (line.get("description") or "").strip()
        code_like = escape_like(code)

        def products(domain):
            return self.Product.search(self._product_domain() + domain)

        # Our own reference or the barcode, when the document states them.
        if own_code:
            yield (
                "internal_reference",
                lambda: products([("default_code", "=ilike", escape_like(own_code))]),
            )
        if barcode:
            yield "barcode", lambda: products([("barcode", "=", barcode)])

        # The price lists of the vendor, once it is known.
        supplier_steps = self.supplier_steps and self.partner
        if code:
            if supplier_steps:
                yield (
                    "supplier_code",
                    lambda: self._supplier_products(
                        [("product_code", "=ilike", code_like)]
                    ),
                )
            yield (
                "internal_reference",
                lambda: products([("default_code", "=ilike", code_like)]),
            )
            yield "barcode", lambda: products([("barcode", "=", code)])
        key = normalize_text(description)
        if key:
            # The same words, whatever the case, the accents or the punctuation.
            like = accent_like(max(key.split(), key=len))
            if supplier_steps:
                yield (
                    "supplier_name",
                    lambda: self._supplier_products(
                        [("product_name", "ilike", like)], name_key=key
                    ),
                )
            yield (
                "name",
                lambda: products([("name", "ilike", like)]).filtered(
                    lambda p: normalize_text(p.name) == key
                ),
            )


class UomResolver:
    def __init__(self, env, sender=None):
        self.env = env
        self.sender = sender
        self.Uom = env["uom.uom"]
        self.aliases = {}
        for xmlid, words in UOM_ALIASES.items():
            uom = env.ref(xmlid, raise_if_not_found=False)
            if uom:
                for word in words:
                    self.aliases[word] = uom

    def learned(self, text):
        """The unit a person chose for ``text`` in the documents of the sender."""
        key = normalize_text(text)
        if not self.sender or not key:
            return self.Uom
        mapping = self.env["ai.message.import.uom.mapping"].search(
            [("sender_id", "=", self.sender.id), ("key", "=", key)], limit=1
        )
        return mapping.uom_id.filtered("active")

    def resolve(self, text):
        """The unit of measure written ``text``, ``None`` when unknown."""
        learned = self.learned(text)
        if learned:
            return learned
        key = normalize_text(BRACKET_PLURAL.sub(r"\1", text or ""))
        if not key:
            return None
        # "c", "cj": the unit of Odoo may be the box itself.
        key = PACKAGING_WORDS.get(key, key)
        if key in self.aliases:
            return self.aliases[key]
        if " " not in key and singular(key) in self.aliases:
            return self.aliases[singular(key)]
        for lang in search_langs(self.env):
            uoms = self.Uom.with_context(lang=lang).search([])
            found = uoms.filtered(lambda u: normalize_text(u.name) == key)
            if len(found) == 1:
                return found
        return None

    def packaging(self, product, text, company, usage="purchase"):
        """The packaging of ``product`` named ``text``, usable for ``usage``
        (``purchase`` or ``sales``).

        A quantity written in ``text`` ("cajas de 12") must be the one of the
        packaging, otherwise the packaging is not the quoted one.

        :return: a ``Match`` with the packaging, or the candidates when several
            packagings fit.
        """
        words = normalize_text(text).split()
        Packaging = self.env["product.packaging"]
        if not words:
            return Match(Packaging)
        root = singular(PACKAGING_WORDS.get(words[0], words[0]))
        found = product.packaging_ids.filtered(
            lambda p: (
                p[usage]
                and p.company_id in (company, self.env["res.company"])
                and normalize_text(p.name)
                and singular(normalize_text(p.name).split()[0]) == root
            )
        )
        quantities = [
            float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", text)
        ]
        if quantities:
            found = found.filtered(
                lambda p: any(
                    float_compare(quantity, p.qty, precision_digits=4) == 0
                    for quantity in quantities
                )
            )
        if len(found) == 1:
            return Match(found, "packaging", found)
        return Match(Packaging, "ambiguous" if found else "", found)


def match_payment_term(env, company, terms):
    """A payment term equivalent to the quoted one.

    :param terms: ``{"text", "days", "end_of_month"}`` from the quote.
    """
    PaymentTerm = env["account.payment.term"]
    candidates = PaymentTerm.search([("company_id", "in", [False, company.id])])
    days = terms.get("days")
    if days is not None:
        delay_type = (
            "days_after_end_of_month" if terms.get("end_of_month") else ("days_after")
        )
        found = candidates.filtered(
            lambda term: (
                len(term.line_ids) == 1
                and not term.early_discount
                and term.line_ids.value == "percent"
                and float_compare(term.line_ids.value_amount, 100.0, precision_digits=2)
                == 0
                and term.line_ids.delay_type == delay_type
                and term.line_ids.nb_days == days
            )
        )
        if found:
            return found.sorted(lambda term: (term.sequence, term.id))[:1]
    text = normalize_text(terms.get("text"))
    if text:
        for lang in search_langs(env):
            found = candidates.with_context(lang=lang).filtered(
                lambda term: normalize_text(term.name) == text
            )
            if found:
                return found.sorted(lambda term: (term.sequence, term.id))[:1]
    return PaymentTerm


def match_warehouse(env, company, address):
    """The warehouses of the company whose name or address is in ``address``."""
    text = normalize_text(address)
    Warehouse = env["stock.warehouse"]
    if not text:
        return Warehouse
    padded = f" {text} "
    compact = text.replace(" ", "")
    found = Warehouse
    for warehouse in Warehouse.search([("company_id", "=", company.id)]):
        name = normalize_text(warehouse.name)
        partner = warehouse.partner_id
        street_words = [
            word for word in normalize_text(partner.street).split() if len(word) > 3
        ]
        zip_code = normalize_code(partner.zip)
        by_name = name and f" {name} " in padded
        by_address = (
            zip_code
            and zip_code in compact
            and street_words
            and any(f" {word} " in padded for word in street_words)
        )
        if by_name or by_address:
            found |= warehouse
    return found
