# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import io
import json
from unittest.mock import patch

from PIL import Image

from odoo.exceptions import UserError
from odoo.orm.model_classes import add_to_registry
from odoo.tests.common import TransactionCase

from ..services import llm_extractor
from .fake_models import AiConnection, FakeExtractionClient


def _make_png_bytes(width=200, height=100, color=(255, 255, 255)):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=color).save(buffer, format="PNG")
    return buffer.getvalue()


class TestAiDocumentExtraction(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        orig_bases = cls.registry[AiConnection._name]._base_classes__
        add_to_registry(cls.registry, AiConnection)
        cls.registry._setup_models__(cls.env.cr, [AiConnection._name])
        cls.registry.init_models(
            cls.env.cr, [AiConnection._name], {"models_to_check": True}
        )

        def cleanup_registry():
            model_cls = cls.registry[AiConnection._name]
            model_cls._base_classes__ = orig_bases
            model_cls._setup_done__ = False
            cls.registry._setup_models__(cls.env.cr, [AiConnection._name])

        cls.addClassCleanup(cleanup_registry)
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Acme Industrial Supplies GmbH",
                "is_company": True,
            }
        )
        cls.journal = cls.env["account.journal"].search(
            [
                ("type", "=", "purchase"),
                ("company_id", "=", cls.env.company.id),
            ],
            limit=1,
        )
        cls.tax_20 = cls.env["account.tax"].create(
            {
                "name": "Purchase VAT 20%",
                "amount": 20.0,
                "amount_type": "percent",
                "type_tax_use": "purchase",
                "company_id": cls.env.company.id,
            }
        )
        cls.connection = cls.env["ai.connection"].create(
            {
                "name": "Test Vision Connection",
                "kind": "fake_extraction",
                "fake_response": json.dumps(
                    {
                        "partner_name": "Acme Industrial Supplies GmbH",
                        "invoice_number": "INV-2026-0042",
                        "payment_reference": "PAY-998877",
                        "invoice_date": "2026-05-15",
                        "amount_untaxed": 100.0,
                        "amount_tax": 20.0,
                        "amount_total": 120.0,
                        "currency": cls.env.company.currency_id.name,
                        "description": "Server hosting services",
                        "lines": [
                            {
                                "name": "Dedicated Server",
                                "quantity": 2,
                                "price_unit": 50.0,
                                "tax_rate": 20.0,
                            }
                        ],
                    }
                ),
            }
        )

    def setUp(self):
        super().setUp()
        FakeExtractionClient.last_messages = None
        FakeExtractionClient.response_queue = None
        self.journal.ai_connection_id = False
        self.env.company.ai_connection_id = False
        self.env.company.ai_fuzzy_match_threshold = 85

    def _create_draft_bill(self, with_attachment=True, filename="invoice.png"):
        move = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "journal_id": self.journal.id,
            }
        )
        attachment = None
        if with_attachment:
            attachment = self.env["ir.attachment"].create(
                {
                    "name": filename,
                    "datas": base64.b64encode(_make_png_bytes(1600, 1200)),
                    "mimetype": "image/png",
                    "res_model": "account.move",
                    "res_id": move.id,
                }
            )
        return move, attachment

    def test_manual_extraction_and_review_wizard_flow(self):
        """Test manual extraction on a draft bill and review wizard."""
        self.env.company.ai_connection_id = self.connection
        move, _attachment = self._create_draft_bill(filename="invoice.png (1)")
        move.action_extract_with_ai()
        self.assertEqual(move.ai_extraction_state, "done")
        self.assertEqual(move.partner_id, self.partner)
        self.assertEqual(move.ref, "INV-2026-0042")
        self.assertEqual(move.payment_reference, "PAY-998877")
        self.assertEqual(str(move.invoice_date), "2026-05-15")
        self.assertEqual(move.ai_extracted_tax, 20.0)
        self.assertEqual(move.ai_extracted_total, 120.0)
        self.assertEqual(len(move.invoice_line_ids), 1)
        line = move.invoice_line_ids[0]
        self.assertEqual(line.name, "Dedicated Server")
        self.assertEqual(line.quantity, 2.0)
        self.assertEqual(line.price_unit, 50.0)
        self.assertIn(self.tax_20, line.tax_ids)
        files = FakeExtractionClient.last_messages[-1]["files"]
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["mimetype"], "image/png")
        action = move.action_review_extraction()
        wizard = self.env["extraction.wizard"].browse(action["res_id"])
        self.assertEqual(wizard.extracted_partner_name, "Acme Industrial Supplies GmbH")
        other_partner = self.env["res.partner"].create(
            {"name": "Alternative Vendor", "is_company": True}
        )
        wizard.partner_id = other_partner
        wizard.action_apply()
        self.assertEqual(move.partner_id, other_partner)

    def test_extend_with_attachments_and_multipage_pdf_flow(self):
        """Test _extend_with_attachments and multi-page PDF rendering."""
        self.journal.ai_connection_id = self.connection
        move, attachment = self._create_draft_bill(filename="multipage.pdf")
        attachment.mimetype = "application/pdf"
        page_images = [
            Image.new("RGB", (800, 1000), color=(255, 255, 255)),
            Image.new("RGB", (800, 1000), color=(240, 240, 240)),
            Image.new("RGB", (800, 1000), color=(220, 220, 220)),
        ]
        with patch(
            "odoo.addons.ai_document_extraction.models.account_move.convert_from_bytes",
            return_value=page_images,
        ):
            extended = move._extend_with_attachments(
                [
                    {
                        "name": "multipage.pdf",
                        "raw": None,
                        "import_file_type": "pdf",
                        "attachment": attachment,
                    }
                ],
                new=True,
            )
        self.assertTrue(extended)
        self.assertEqual(move.ai_extraction_state, "done")
        files = FakeExtractionClient.last_messages[-1]["files"]
        self.assertEqual(len(files), 3)
        self.assertEqual(
            [f["name"] for f in files],
            [
                "multipage_page_1.png",
                "multipage_page_2.png",
                "multipage_page_3.png",
            ],
        )

    def test_retry_and_error_handling_flow(self):
        """Test retry on invalid LLM output, fallback fields, and error logging."""
        self.env.company.ai_connection_id = self.connection
        eur = self.env.ref("base.EUR")
        usd = self.env.ref("base.USD")
        eur.active = True
        usd.active = True
        foreign_currency = usd if self.env.company.currency_id == eur else eur
        FakeExtractionClient.response_queue = [
            "not valid json at all",
            json.dumps(
                {
                    "partner_name": "Unknown SingleWordVendor",
                    "invoice_number": None,
                    "payment_reference": "TX-777",
                    "invoice_date": None,
                    "amount_untaxed": "75,50",
                    "amount_tax": "0",
                    "amount_total": "75,50",
                    "currency": foreign_currency.name,
                    "description": "Consulting fee",
                    "lines": [],
                }
            ),
        ]
        move, _attachment = self._create_draft_bill()
        move.action_extract_with_ai()
        self.assertEqual(move.ai_extraction_state, "done")
        self.assertEqual(move.ref, "TX-777")
        self.assertEqual(move.currency_id, foreign_currency)
        self.assertEqual(len(move.invoice_line_ids), 1)
        self.assertEqual(move.invoice_line_ids[0].price_unit, 75.5)
        FakeExtractionClient.response_queue = [
            "bad json 1",
            "bad json 2",
        ]
        with self.assertLogs(
            "odoo.addons.ai_document_extraction.models.account_move",
            level="WARNING",
        ):
            move.action_extract_with_ai()
        self.assertEqual(move.ai_extraction_state, "error")

    def test_validation_guards_and_parser(self):
        """Test action guards, settings inheritance, and LLM validation helpers."""
        move, _attachment = self._create_draft_bill(with_attachment=False)
        with self.assertRaises(UserError):
            move.action_extract_with_ai()
        move_with_att, _att = self._create_draft_bill(with_attachment=True)
        with self.assertRaises(UserError):
            move_with_att.action_extract_with_ai()
        entry = self.env["account.move"].create({"move_type": "entry"})
        with self.assertRaises(UserError):
            entry.action_extract_with_ai()
        settings = self.env["res.config.settings"].create(
            {
                "ai_connection_id": self.connection.id,
                "ai_fuzzy_match_threshold": 90,
            }
        )
        settings.execute()
        self.assertEqual(self.env.company.ai_connection_id, self.connection)
        self.assertEqual(self.env.company.ai_fuzzy_match_threshold, 90)
        parsed = llm_extractor.parse_and_validate(
            'Prefix {broken} {"partner_name": "qwen3-vl", '
            '"invoice_number": "http://bad", '
            '"payment_reference": "REF-1", "invoice_date": "1990-01-01", '
            '"currency": "INVALID", '
            '"lines": ["skip", {"name": "Item", "tax_id": "bad", "tax_rate": "bad"}]}',
            available_taxes=[
                {"id": 1, "name": "VAT", "amount": 20.0, "amount_type": "percent"}
            ],
            available_currencies=["EUR", "USD"],
        )
        self.assertIsNone(parsed["partner_name"])
        self.assertIsNone(parsed["invoice_number"])
        self.assertEqual(parsed["payment_reference"], "REF-1")
        self.assertIsNone(parsed["invoice_date"])
        self.assertIsNone(parsed["currency"])
        self.assertNotIn("tax_id", parsed["lines"][1])
        self.assertNotIn("tax_rate", parsed["lines"][1])

        # Additional parser & helper edge cases
        parsed_non_list = llm_extractor.parse_and_validate(
            '{"invoice_date": "bad-date", "lines": "not-a-list"}'
        )
        self.assertEqual(parsed_non_list["lines"], [])
        self.assertIsNone(parsed_non_list["invoice_date"])

        self.env.company.ai_connection_id = False
        self.assertFalse(move._ai_connection(raise_if_missing=False))
        self.assertIsNone(move._ai_to_float(True))
        self.assertIsNone(move._ai_to_float("abc"))
        self.assertIsNone(move._ai_to_float(None))
        self.assertIsNone(move._match_partner("", 85))
        self.assertEqual(move._ai_resolve_tax(tax_id=self.tax_20.id), self.tax_20)
        self.assertFalse(move._ai_resolve_tax(tax_id="bad", tax_rate="bad"))
        move._ai_set_lines([{"name": "Empty", "quantity": None, "price_unit": None}])
        move._apply_extraction({"invoice_date": "bad-date"})

        # _extend_with_attachments edge cases (empty, non-processable, no connection)
        self.assertFalse(move._extend_with_attachments([]))
        self.assertFalse(
            move._extend_with_attachments(
                [{"name": "notes.txt", "raw": None, "import_file_type": "txt"}]
            )
        )
        self.assertTrue(
            move_with_att._extend_with_attachments(
                [{"name": "invoice.png", "raw": None, "import_file_type": "png"}]
            )
        )

        # Fallback mimetype, broken raw_extraction in review, non-draft apply
        _att.mimetype = "application/octet-stream"
        self.assertEqual(move_with_att._ai_get_attachment(), _att)
        move_with_att.ai_raw_extraction = "{not-json"
        action = move_with_att.action_review_extraction()
        wizard = self.env["extraction.wizard"].browse(action["res_id"])
        with patch.object(type(move_with_att), "state", "posted"):
            with self.assertRaises(UserError):
                move_with_att.action_extract_with_ai()
            close_act = wizard.action_apply()
            self.assertEqual(close_act["type"], "ir.actions.act_window_close")

        # Empty attachment & empty PDF pages errors
        with patch(
            "odoo.addons.ai_document_extraction.models.account_move.convert_from_bytes",
            return_value=[],
        ):
            _att.name = "empty.pdf"
            with self.assertRaises(UserError):
                move_with_att._ai_prepare_attachments(_att)
        empty_att = self.env["ir.attachment"].new({"name": "empty.png"})
        with self.assertRaises(UserError):
            move_with_att._ai_prepare_attachments(empty_att)
