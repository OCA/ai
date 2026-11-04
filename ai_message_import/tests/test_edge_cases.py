# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged

from ..services import document_processor as docs
from ..services import matching
from ..services.order_builder import OrderBuilder
from ..services.pricing import CurrencyConverter, global_discount_rate
from ..services.product_chooser import same_word, similarity
from ..services.quote_schema import SCHEMA_VERSION
from ..services.quote_validator import (
    MAX_LINES,
    MAX_QUOTES,
    AIResponseError,
    parse_number,
    validate_response,
)
from ..services.tools import same_vat, vat_variants
from .test_services import S, W, _xlsx, _zip


class FakeSheet:
    def __init__(self, name, rows):
        self.name = name
        self.rows = rows
        self.nrows = len(rows)

    def row_values(self, index):
        return self.rows[index]


class FakeXlrd:
    """``xlrd`` reading a workbook of one sheet."""

    def __init__(self, *rows):
        self.rows = rows

    def open_workbook(self, file_contents=None, on_demand=False):
        sheet = FakeSheet("Pedido", list(self.rows))
        return type("Book", (), {"sheets": lambda book: [sheet]})()


@tagged("post_install", "-at_install")
class TestEdgeCases(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

    # ------------------------------------------------------------------
    # Answers of the AI
    # ------------------------------------------------------------------

    def _quote(self, **values):
        data = {
            "quote_key": "Q1",
            "relation": "new",
            "partner": {"name": "Vendor", "confidence": 0.9},
            "lines": [{"description": "Item", "quantity": 2, "confidence": 0.9}],
            "confidence": 0.9,
        }
        data.update(values)
        return data

    def _answer(self, *quotes):
        return {"schema_version": SCHEMA_VERSION, "quotes": list(quotes)}

    def test_numbers_that_are_not_numbers(self):
        self.assertIsNone(parse_number(["1"]))
        self.assertIsNone(parse_number("none"))
        self.assertEqual(parse_number("1.250,5"), 1250.5)

    def test_answers_beyond_the_limits_are_refused(self):
        for wrong in (
            self._answer(self._quote(lines=["text"])),
            self._answer(self._quote(lines=[{"quantity": 1}] * (MAX_LINES + 1))),
            self._answer(*[self._quote()] * (MAX_QUOTES + 1)),
        ):
            with self.assertRaises(AIResponseError):
                validate_response(self.env, wrong)

    def test_doubtful_values_are_warned(self):
        result = validate_response(
            self.env,
            self._answer(
                self._quote(
                    relation="merge",
                    delivery={"date": "next week"},
                    lines=[
                        {
                            "description": "Item",
                            "quantity": 2,
                            "delivery_date": "soon",
                        }
                    ],
                ),
                self._quote(),
            ),
        )
        first, second = result["quotes"]
        self.assertEqual(first["relation"], "new")
        self.assertTrue(first["delivery"]["date_is_ambiguous"])
        self.assertEqual(len(first["warnings"]), 2)
        self.assertTrue(first["lines"][0]["warnings"])
        self.assertEqual(second["quote_key"], "Q1-2", "The keys stay unique")

    def test_vat_numbers(self):
        self.assertEqual(vat_variants("ES B12345674"), {"ESB12345674", "B12345674"})
        self.assertFalse(same_vat("", "B12345674"))
        self.assertTrue(same_vat("ESB12345674", "B12345674"))

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    def _prepare(self, name, data, **options):
        attachment = self.env["ir.attachment"].create({"name": name, "raw": data})
        return docs.DocumentProcessor(self.env, **options).prepare([("D1", attachment)])

    def test_texts_in_any_encoding(self):
        self.assertEqual(docs.decode_text(b"\x81ok"), "\x81ok")
        self.assertIsNone(docs._sniff_zip(_zip({"notes.txt": "text"})))

    def test_word_document_with_tabs_and_footer(self):
        data = _zip(
            {
                "word/document.xml": (
                    f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>Ref</w:t>'
                    "<w:tab/><w:t>Qty</w:t></w:r></w:p></w:body></w:document>"
                ),
                "word/footer1.xml": (
                    f'<w:ftr xmlns:w="{W}"><w:p><w:r><w:t>Page 1</w:t></w:r>'
                    "</w:p></w:ftr>"
                ),
            }
        )
        documents, _issues = self._prepare("oferta.docx", data)
        self.assertEqual(documents[0].text, "Ref\tQty\nPage 1")

    def test_spreadsheet_limits(self):
        data = _zip(
            {
                "xl/workbook.xml": (
                    f'<workbook xmlns="{S}" xmlns:r="http://schemas.openxmlformats.'
                    'org/officeDocument/2006/relationships"><sheets>'
                    '<sheet name="Missing" sheetId="1" r:id="rId9"/>'
                    '<sheet name="Oferta" sheetId="2" r:id="rId1"/></sheets>'
                    "</workbook>"
                ),
                "xl/_rels/workbook.xml.rels": (
                    '<Relationships xmlns="http://schemas.openxmlformats.org/'
                    'package/2006/relationships"><Relationship Id="rId1" '
                    'Target="worksheets/sheet1.xml" Type="worksheet"/>'
                    "</Relationships>"
                ),
                "xl/worksheets/sheet1.xml": (
                    f'<worksheet xmlns="{S}"><sheetData>'
                    '<row r="1"><c r="A1" t="inlineStr"><is><t>Inline</t></is></c>'
                    "</row>"
                    '<row r="2"><c r="A2"><v>2</v></c></row>'
                    "</sheetData></worksheet>"
                ),
            }
        )
        with patch.object(docs, "MAX_SHEET_ROWS", 1):
            documents, _issues = self._prepare("oferta.xlsx", data)
        self.assertEqual(documents[0].text, "Sheet: Oferta\nInline")
        self.assertIn("Sheet: Oferta", self._prepare("x.xlsx", _xlsx())[0][0].text)

    def test_old_spreadsheet(self):
        ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 40
        fake = FakeXlrd(["Ref", 3.0, 2.5], ["", "", ""], [" X ", "", ""])
        with patch.object(docs, "xlrd", fake), patch.object(docs, "MAX_SHEET_ROWS", 2):
            documents, _issues = self._prepare("pedido.xls", ole)
        self.assertEqual(documents[0].text, "Sheet: Pedido\nRef | 3 | 2.5")
        with patch.object(docs, "xlrd", None):
            documents, issues = self._prepare("pedido.xls", ole)
        self.assertFalse(documents)
        self.assertTrue(issues)

    def test_files_left_out(self):
        ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 40
        client = type("Client", (), {"native_types": ()})
        cases = [
            ("empty.txt", b"", {}, "empty"),
            ("blank.txt", b"  \n ", {}, "no readable text"),
            ("virus.exe", b"MZ\x90\x00", {}, "not supported"),
            ("order.pdf", b"%PDF-1.7", {"client": client}, "does not read"),
            ("pedido.msg", ole, {}, ""),
            ("broken.docx", _zip({"word/document.xml": "<w:document"}), {}, "damaged"),
        ]
        for name, data, options, reason in cases:
            documents, issues = self._prepare(name, data, **options)
            self.assertFalse(documents, name)
            self.assertIn(reason, issues[0][2], name)

    def test_size_of_the_conversation(self):
        processor = docs.DocumentProcessor(self.env, max_total_size_mb=10 / docs.MB)
        attachments = self.env["ir.attachment"].create(
            [
                {"name": "a.txt", "raw": b"12345678"},
                {"name": "b.txt", "raw": b"12345678"},
            ]
        )
        documents, issues = processor.prepare(
            [("D1", attachments[0]), ("D2", attachments[1])]
        )
        self.assertEqual([d.label for d in documents], ["D1"])
        self.assertEqual(issues[0][0], "D2")

    # ------------------------------------------------------------------
    # Prices and currencies
    # ------------------------------------------------------------------

    def test_global_discount_that_does_not_match(self):
        lines = [{"quantity": 1, "price_unit": 100.0}]
        self.assertEqual(
            global_discount_rate({"percent": 10, "amount": 99}, lines),
            (None, 100.0, "mismatch"),
        )
        self.assertEqual(
            global_discount_rate({"percent": 10, "amount": 10}, lines),
            (10, 100.0, None),
        )

    def test_unknown_currency(self):
        converter = CurrencyConverter(self.env, self.company, "XYZ")
        self.assertIsNone(converter.convert(10.0))
        self.assertIn("XYZ", converter.describe())
        own = CurrencyConverter(self.env, self.company, None)
        self.assertEqual(own.describe(), "")
        self.assertEqual(own.convert(10.0), 10.0)

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def test_partner_that_cannot_be_created(self):
        partners = matching.PartnerMatcher(
            self.env, self.company, self.env["mail.message.import.sender"]
        )
        self.assertEqual(partners.create_blocker({"name": ""}, 0.5), "name")
        own = {"name": self.company.name, "confidence": 1.0}
        self.assertEqual(partners.create_blocker(own, 0.5), "own")

    def test_partner_created_without_a_refused_vat(self):
        partners = matching.PartnerMatcher(
            self.env, self.company, self.env["mail.message.import.sender"]
        )
        Partner = type(self.env["res.partner"])
        create = Partner.create

        def refuse_vat(records, vals_list):
            values = [vals_list] if isinstance(vals_list, dict) else vals_list
            if any(vals.get("vat") for vals in values):
                # The check of a localisation; not a message of the module.
                error = "Invalid VAT"
                raise ValidationError(error)
            return create(records, vals_list)

        with patch.object(Partner, "create", refuse_vat):
            partner, note = partners.create_partner(
                {"name": "New Vendor SL", "vat": "XX123", "country_code": "ES"}
            )
        self.assertEqual(partner.name, "New Vendor SL")
        self.assertFalse(partner.vat)
        self.assertEqual(partner.country_id, self.env.ref("base.es"))
        self.assertIn("XX123", note)

    def test_units_and_packagings(self):
        resolver = matching.UomResolver(self.env)
        unit = self.env.ref("uom.product_uom_unit")
        self.assertEqual(resolver.resolve("unids"), unit, "Plural of a known word")
        product = self.env["product.product"].create({"name": "Nail"})
        self.assertFalse(resolver.packaging(product, "", self.company).record)

    def test_payment_term_by_name(self):
        term = self.env.ref("account.account_payment_term_30days")
        self.assertEqual(
            matching.match_payment_term(
                self.env, self.company, {"text": term.with_context(lang="en_US").name}
            ),
            term,
        )

    def test_similar_words(self):
        self.assertEqual(same_word("box", "box"), 1.0)
        self.assertEqual(similarity(([], set()), (["box"], set())), 0.0)

    # ------------------------------------------------------------------
    # Rules of each document type
    # ------------------------------------------------------------------

    def test_rules_given_by_the_document_types(self):
        document = self.env["ai.message.import.document"].new(
            {"company_id": self.company.id}
        )
        builder = OrderBuilder(document)
        line = self.env["ai.message.import.document.line"]
        for hook, args in (
            ("_role", ()),
            ("_order_label", ()),
            ("_header_values", (None,)),
            ("_default_payment_term", (None,)),
            ("_create_product", (None, None)),
            ("_recompute_line_prices", (None,)),
            ("_price_origin", (None,)),
            ("_freight_line_values", (None, None, 0.0)),
            ("_freight_tax_rate", (None, None)),
            ("_order_values", (None, None)),
        ):
            with self.assertRaises(NotImplementedError, msg=hook):
                getattr(builder, hook)(*args)
        self.assertFalse(builder._auto_create_partner())
        self.assertEqual(builder._partner_min_confidence(), 1.0)
        self.assertEqual(builder._odoo_discount(line), 0.0)
        self.assertTrue(builder._product_creation_blocker(line, None))
