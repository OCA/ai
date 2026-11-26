# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import io
import zipfile
from email.message import EmailMessage
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.mail_message_import.services import email_reader

from ..services import document_processor as docs
from ..services.ai_client import AIClient, AIError, data_part, text_part
from ..services.matching import UomResolver
from ..services.pricing import combine_discounts, global_discount_rate
from ..services.quote_schema import (
    SCHEMA_VERSION,
    response_schema,
    system_instruction,
)
from ..services.quote_validator import AIResponseError, validate_response
from .common import FakeConnection

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _forwarded_email():
    """An email forwarded from a mailbox: logo, order in a PDF, attached email."""
    inner = EmailMessage()
    inner["From"] = "Almacén Dofo <almacen@dofo.example>"
    inner["Subject"] = "Pedido Dofo jueves"
    inner.set_content("Adjunto pedido.")
    inner.add_attachment(
        b"%PDF-1.7 inner order",
        maintype="application",
        subtype="pdf",
        filename="dofo.pdf",
    )
    outer = EmailMessage()
    outer["From"] = "Pedidos <pedidos@company.example>"
    outer["To"] = "admin@company.example"
    outer["Subject"] = "RV: Pedido compra 1026-AL0796"
    outer.set_content(
        "Un saludo, Administración <https://urldefense.example/"
        + "x" * 80
        + ">\n\nDe: pedidos@hotel.example\nAsunto: Pedido compra 1026-AL0796"
    )
    outer.add_attachment(
        b"\x89PNG\r\n\x1a\n" + b"0" * 2000,
        maintype="image",
        subtype="png",
        filename="image001.png",
    )
    outer.add_attachment(
        b"%PDF-1.7 order",
        maintype="application",
        subtype="pdf",
        filename="Pedido compra 1026-AL0796.pdf",
    )
    outer.add_attachment(inner)
    return outer.as_bytes()


def _docx():
    return _zip(
        {
            "[Content_Types].xml": "<Types/>",
            "word/document.xml": (
                f'<w:document xmlns:w="{W}"><w:body>'
                "<w:p><w:r><w:t>Presupuesto 2026-15</w:t></w:r></w:p>"
                "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>REF-1</w:t></w:r></w:p></w:tc>"
                "<w:tc><w:p><w:r><w:t>10 uds</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
                "</w:body></w:document>"
            ),
            "word/header1.xml": (
                f'<w:hdr xmlns:w="{W}"><w:p><w:r><w:t>Ferreteria Norte</w:t></w:r>'
                "</w:p></w:hdr>"
            ),
        }
    )


def _xlsx():
    return _zip(
        {
            "[Content_Types].xml": "<Types/>",
            "xl/workbook.xml": (
                f'<workbook xmlns="{S}" xmlns:r="{R}"><sheets>'
                '<sheet name="Oferta" sheetId="1" r:id="rId1"/></sheets></workbook>'
            ),
            "xl/_rels/workbook.xml.rels": (
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                'relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" '
                'Type="worksheet"/></Relationships>'
            ),
            "xl/sharedStrings.xml": (
                f'<sst xmlns="{S}"><si><t>Ref</t></si><si><t>Qty</t></si>'
                "<si><t>REF-1</t></si></sst>"
            ),
            "xl/worksheets/sheet1.xml": (
                f'<worksheet xmlns="{S}"><sheetData>'
                '<row r="1"><c r="A1" t="s"><v>0</v></c>'
                '<c r="B1" t="s"><v>1</v></c></row>'
                '<row r="2"><c r="A2" t="s"><v>2</v></c>'
                '<c r="C2"><v>12.5</v></c></row>'
                "</sheetData></worksheet>"
            ),
        }
    )


@tagged("post_install", "-at_install")
class TestServices(TransactionCase):
    # ------------------------------------------------------------------
    # Validation of the answers of the AI
    # ------------------------------------------------------------------

    def _answer(self, **quote):
        data = {
            "quote_key": "Q1",
            "document_type": "purchase",
            "relation": "new",
            "partner": {"name": "Vendor", "confidence": 0.9},
            "lines": [{"description": "Item", "quantity": 2, "confidence": 0.9}],
            "confidence": 0.9,
        }
        data.update(quote)
        return {"schema_version": SCHEMA_VERSION, "quotes": [data]}

    def test_answer_structure_is_enforced(self):
        for wrong in (
            [],
            {"quotes": []},
            {"schema_version": "9.9", "quotes": []},
            {"schema_version": SCHEMA_VERSION, "quotes": {}},
            {"schema_version": SCHEMA_VERSION, "quotes": ["text"]},
            self._answer(lines="none"),
            self._answer(partner="name"),
        ):
            with self.assertRaises(AIResponseError):
                validate_response(self.env, wrong)

    def test_document_type_must_be_installed(self):
        result = validate_response(
            self.env, self._answer(), document_types=["purchase", "sale"]
        )
        self.assertEqual(result["quotes"][0]["document_type"], "purchase")
        with self.assertRaises(AIResponseError):
            validate_response(
                self.env, self._answer(document_type="invoice"), document_types=["sale"]
            )

    def test_instructions_list_the_document_types(self):
        descriptions = {
            "purchase": "A quote of a vendor.",
            "sale": "An order of a\n  customer.",
        }
        text = system_instruction(
            'Types:\n{types}\nSchema "{version}", {"other": "braces"}', descriptions
        )
        self.assertIn('- "purchase": A quote of a vendor.', text)
        self.assertIn('- "sale": An order of a customer.', text)
        self.assertIn(f'Schema "{SCHEMA_VERSION}"', text)
        self.assertIn('{"other": "braces"}', text, "Other braces are kept")
        types = {key: {} for key in descriptions}
        schema = response_schema(types)
        item = schema["properties"]["quotes"]["items"]
        self.assertEqual(
            item["properties"]["document_type"]["enum"], ["purchase", "sale"]
        )
        self.assertIn("document_type", item["required"])

    def test_values_are_validated(self):
        result = validate_response(
            self.env,
            self._answer(
                lines=[
                    {
                        "description": "Valid",
                        "quantity": "1.250,5",
                        "price_unit": "3,5",
                    },
                    {"description": "No quantity", "quantity": 0},
                    {"quantity": 1},
                    {
                        "description": "Bad discount",
                        "quantity": 1,
                        "discount_percent": 150,
                    },
                ],
                currency="Euros",
                quote_date="31/02/2026",
                message_refs=["M1", "M7"],
                target_reference="AID/OTHER",
                relation="update",
            ),
            message_labels=["M1"],
            target_references=["AID/1"],
        )
        quote = result["quotes"][0]
        valid, no_qty, no_text, bad_discount = quote["lines"]
        self.assertEqual(valid["quantity"], 1250.5)
        self.assertEqual(valid["price_unit"], 3.5)
        self.assertFalse(valid["errors"])
        self.assertTrue(no_qty["errors"])
        self.assertTrue(no_text["errors"])
        self.assertIsNone(bad_discount["discount_percent"])
        self.assertTrue(bad_discount["warnings"])
        self.assertEqual(quote["currency"], "")
        self.assertIsNone(quote["quote_date"])
        self.assertEqual(quote["message_refs"], ["M1"])
        self.assertIsNone(
            quote["target_reference"], "Only known documents can be corrected"
        )

    def test_texts_are_cleaned(self):
        result = validate_response(
            self.env,
            self._answer(
                partner={"name": "Ven\x00dor\x07 " + "x" * 500, "confidence": 3}
            ),
        )
        partner = result["quotes"][0]["partner"]
        self.assertTrue(partner["name"].startswith("Vendor"))
        self.assertLessEqual(len(partner["name"]), 256)
        self.assertEqual(partner["confidence"], 1.0)

    # ------------------------------------------------------------------
    # Documents
    # ------------------------------------------------------------------

    def _attachment(self, name, data):
        return self.env["ir.attachment"].create({"name": name, "raw": data})

    def test_word_document_is_read(self):
        documents, issues = docs.DocumentProcessor(self.env).prepare(
            [("D1", self._attachment("oferta.docx", _docx()))]
        )
        self.assertFalse(issues)
        text = documents[0].text
        self.assertIn("Ferreteria Norte", text)
        self.assertIn("Presupuesto 2026-15", text)
        self.assertIn("REF-1 | 10 uds", text)
        self.assertEqual(documents[0].parts()[0]["text"].count("<<<BEGIN D1>>>"), 1)

    def test_spreadsheet_is_read(self):
        documents, _issues = docs.DocumentProcessor(self.env).prepare(
            [("D1", self._attachment("oferta.xlsx", _xlsx()))]
        )
        text = documents[0].text
        self.assertIn("Sheet: Oferta", text)
        self.assertIn("Ref | Qty", text)
        self.assertIn("REF-1 |  | 12.5", text)

    def test_forwarded_email_is_read(self):
        data = _forwarded_email()
        self.assertEqual(docs.sniff_mimetype(data, "RV pedido"), email_reader.EML)
        content = email_reader.read_email(data, email_reader.EML)
        self.assertIn("Subject: RV: Pedido compra 1026-AL0796", content.text)
        self.assertIn("De: pedidos@hotel.example", content.text)
        self.assertIn("Attached email", content.text)
        self.assertIn("From: Almacén Dofo <almacen@dofo.example>", content.text)
        self.assertNotIn("urldefense", content.text)
        self.assertEqual(
            [file.name for file in content.files],
            ["Pedido compra 1026-AL0796.pdf", "dofo.pdf"],
            "The logo of the signature is left out",
        )
        documents, issues = docs.DocumentProcessor(self.env).prepare(
            [("D1", self._attachment("RV pedido.eml", data))]
        )
        self.assertFalse(issues)
        self.assertIn("Subject: RV: Pedido", documents[0].text)

    def test_outlook_email_is_not_an_old_word_document(self):
        ole = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 40
        outlook = ole + "__substg1.0_0037001F".encode("utf-16-le")
        self.assertEqual(docs.sniff_mimetype(outlook, "RV pedido"), email_reader.MSG)
        self.assertEqual(docs.sniff_mimetype(ole, "pedido.msg"), email_reader.MSG)
        self.assertEqual(docs.sniff_mimetype(ole, "pedido.doc"), docs.DOC)

    def test_pdf_and_images_go_to_the_ai_as_they_are(self):
        documents, _issues = docs.DocumentProcessor(self.env).prepare(
            [("D1", self._attachment("x.bin", b"%PDF-1.7 data"))]
        )
        part = documents[0].parts()[1]
        self.assertEqual(part["mimetype"], "application/pdf")
        self.assertEqual(part["data"], b"%PDF-1.7 data")

    def test_audio_is_not_sent_to_the_ai(self):
        audio = [("D1", self._attachment("nota.ogg", b"OggS" + b"\x00" * 20))]
        image = [("D2", self._attachment("x.png", b"\x89PNG\r\n\x1a\n0000"))]
        processor = docs.DocumentProcessor(self.env, client=AIClient)
        documents, issues = processor.prepare(audio)
        self.assertFalse(documents)
        self.assertIn("does not read", issues[0][2])
        documents, issues = processor.prepare(image)
        self.assertEqual(documents[0].mimetype, "image/png")

    def test_files_are_controlled(self):
        processor = docs.DocumentProcessor(
            self.env, max_file_size_mb=1, max_total_size_mb=1
        )
        documents, issues = processor.prepare(
            [
                ("D1", self._attachment("old.doc", b"\xd0\xcf\x11\xe0" + b"\x00" * 20)),
                ("D2", self._attachment("big.pdf", b"%PDF" + b"0" * (2 * docs.MB))),
                ("D3", self._attachment("virus.exe", b"MZ\x90\x00")),
                ("D4", self._attachment("fake.pdf", b"PK\x03\x04not a zip")),
                ("D5", self._attachment("ok.txt", "Línea 1".encode("cp1252"))),
            ]
        )
        self.assertEqual([d.label for d in documents], ["D5"])
        self.assertEqual(documents[0].text, "Línea 1")
        self.assertEqual([issue[0] for issue in issues], ["D1", "D2", "D3", "D4"])

    def test_zip_bomb_is_refused(self):
        with patch.object(docs, "MAX_ZIP_MEMBER_SIZE", 10):
            documents, issues = docs.DocumentProcessor(self.env).prepare(
                [("D1", self._attachment("oferta.docx", _docx()))]
            )
        self.assertFalse(documents)
        self.assertIn("too large", issues[0][2])

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------

    def test_discounts(self):
        self.assertAlmostEqual(combine_discounts(10, 5), 14.5)
        self.assertAlmostEqual(combine_discounts(0, 5), 5)
        lines = [
            {"quantity": 10, "price_unit": 10, "discount_percent": 10},
            {"quantity": 1, "price_unit": 10},
        ]
        self.assertEqual(global_discount_rate({}, lines), (None, None, None))
        rate, base, error = global_discount_rate({"amount": 10}, lines)
        self.assertAlmostEqual(base, 100)
        self.assertAlmostEqual(rate, 10)
        self.assertIsNone(error)
        self.assertEqual(
            global_discount_rate({"percent": 5, "amount": 50}, lines)[2], "mismatch"
        )
        self.assertEqual(
            global_discount_rate({"amount": 5}, [{"quantity": 1}])[2], "no_base"
        )
        self.assertEqual(global_discount_rate({"amount": 500}, lines)[2], "too_large")

    def test_units_with_the_plural_in_brackets(self):
        resolver = UomResolver(self.env)
        unit = self.env.ref("uom.product_uom_unit")
        hour = self.env.ref("uom.product_uom_hour")
        for text, uom in [
            ("Hora(s)", hour),
            ("HORA(S)", hour),
            ("Unidad(es).", unit),
            ("Ud(s)", unit),
            ("uds", unit),
        ]:
            self.assertEqual(resolver.resolve(text), uom, text)

    # ------------------------------------------------------------------
    # The AI connection
    # ------------------------------------------------------------------

    def test_request_to_the_ai_connection(self):
        connection = FakeConnection('```json\n{"quotes": []}\n```', tokens=(90, 10))
        client = AIClient(connection)
        data, raw_text, tokens = client.generate_json(
            "Extract the documents.",
            [
                text_part("Messages"),
                text_part("D1 (order.pdf)"),
                data_part("application/pdf", b"%PDF-1.7", "order.pdf"),
                text_part("D2 (photo.png)"),
                data_part("image/png", b"\x89PNG"),
            ],
            {"type": "object"},
        )
        self.assertEqual(data, {"quotes": []})
        self.assertIn("```json", raw_text)
        self.assertEqual(tokens, 100)
        system, first, second = connection.calls[0]
        self.assertEqual(system["role"], "system")
        self.assertIn('{"type": "object"}', system["content"])
        self.assertEqual(first["content"], "Messages\n\nD1 (order.pdf)")
        self.assertEqual(
            first["files"],
            [
                {
                    "name": "order.pdf",
                    "content": "JVBERi0xLjc=",
                    "mimetype": "application/pdf",
                }
            ],
        )
        self.assertEqual(second["content"], "D2 (photo.png)")
        self.assertEqual(second["files"][0]["name"], "file")
        self.assertIn("test-model", repr(client))

    def test_errors_of_the_ai_connection(self):
        with self.assertRaises(AIError) as error:
            AIClient(self.env["ai.connection"])
        self.assertFalse(error.exception.retryable)

        def provider_error(status_code):
            error = RuntimeError("secret-key in a message")
            error.status_code = status_code
            return error

        for answer, retryable in (
            (provider_error(429), True),
            (provider_error(401), False),
            (ConnectionError("down"), True),
        ):
            client = AIClient(FakeConnection(answer))
            with self.assertRaises(AIError) as error:
                client.generate_json("i", [text_part("x")], {})
            self.assertEqual(error.exception.retryable, retryable)
            self.assertNotIn("secret-key", str(error.exception))
        for answer in ("not json", "[1, 2]"):
            with self.assertRaises(AIError):
                AIClient(FakeConnection(answer)).generate_json("i", [], {})
