# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import os
from unittest import mock

from odoo.tests import TransactionCase


class TestLlmExtractor(TransactionCase):
    def test_parse_json_from_noisy_content(self):
        from ..services import llm_extractor

        content = (
            "Sure! Here is the JSON:\n"
            '{"partner_name": "Voslo Lojistik", "invoice_number": "FT-123", '
            '"invoice_date": "2023-10-25", "amount_untaxed": 100.0, '
            '"amount_tax": 18.0, "amount_total": 118.0, "currency": "TRY"}'
        )
        data = llm_extractor._parse_json_response(content)
        self.assertEqual(data["partner_name"], "Voslo Lojistik")
        self.assertEqual(data["amount_total"], 118.0)

    def test_parse_json_missing_fields_defaults_null(self):
        from ..services import llm_extractor

        data = llm_extractor._parse_json_response('{"invoice_number": "X1"}')
        for field in llm_extractor.EXPECTED_FIELDS:
            self.assertIn(field, data)

    def test_parse_defaults_payment_reference_to_none(self):
        from ..services import llm_extractor

        data = llm_extractor._parse_json_response('{"invoice_number": "X1"}')
        self.assertIsNone(data["payment_reference"])

    def test_parse_json_raises_without_object(self):
        from ..services import llm_extractor

        with self.assertRaises(ValueError):
            llm_extractor._parse_json_response("I am sorry, I cannot do that.")

    def test_parse_json_ignores_trailing_braces(self):
        from ..services import llm_extractor

        content = '{"invoice_number": "FT-1"} but note {this} and more'
        data = llm_extractor._parse_json_response(content)
        self.assertEqual(data["invoice_number"], "FT-1")

    def test_parse_json_code_fence(self):
        from ..services import llm_extractor

        content = '```json\n{"invoice_number": "FT-2"}\n```'
        data = llm_extractor._parse_json_response(content)
        self.assertEqual(data["invoice_number"], "FT-2")

    def test_parse_json_raises_for_list(self):
        from ..services import llm_extractor

        with self.assertRaises(ValueError):
            llm_extractor._parse_json_response("[1, 2, 3]")

    def test_prompt_asks_for_receipt_and_payment_reference(self):
        from ..services import llm_extractor

        self.assertIn("Receipt", llm_extractor.SYSTEM_PROMPT)
        self.assertIn("payment_reference", llm_extractor.SYSTEM_PROMPT)
        self.assertNotIn("never a URL or hash", llm_extractor.SYSTEM_PROMPT)

    def test_validate_keeps_hash_invoice_number(self):
        from ..services import llm_extractor

        data = {
            "invoice_number": "2054148b703b43e690b244ff544d2a9f",
            "partner_name": "VOSLO LOJISTIK A.S.",
            "invoice_date": "2023-10-25",
        }
        result = llm_extractor._validate_data(data)
        self.assertEqual(result["invoice_number"], "2054148b703b43e690b244ff544d2a9f")

    def test_validate_rejects_url_invoice_number(self):
        from ..services import llm_extractor

        result = llm_extractor._validate_data(
            {"invoice_number": "https://files.example.com/invoice.pdf"}
        )
        self.assertIsNone(result["invoice_number"])

    def test_validate_rejects_url_payment_reference(self):
        from ..services import llm_extractor

        result = llm_extractor._validate_data(
            {"payment_reference": "https://files.example.com/pay.pdf"}
        )
        self.assertIsNone(result["payment_reference"])

    def test_validate_rejects_model_name_partner(self):
        from ..services import llm_extractor

        result = llm_extractor._validate_data(
            {"partner_name": "DeepSeek", "invoice_date": "2023-10-25"}
        )
        self.assertIsNone(result["partner_name"])

    def test_validate_rejects_single_token_logo_partner(self):
        from ..services import llm_extractor

        result = llm_extractor._validate_data({"partner_name": "voslo"})
        self.assertIsNone(result["partner_name"])

    def test_validate_keeps_full_company_issuer(self):
        from ..services import llm_extractor

        result = llm_extractor._validate_data({"partner_name": "VOSLO LOJISTIK A.S."})
        self.assertEqual(result["partner_name"], "VOSLO LOJISTIK A.S.")

    def test_validate_rejects_out_of_range_date(self):
        from ..services import llm_extractor

        result = llm_extractor._validate_data({"invoice_date": "2099-01-01"})
        self.assertIsNone(result["invoice_date"])

    def test_validate_rejects_bad_date_format(self):
        from ..services import llm_extractor

        result = llm_extractor._validate_data({"invoice_date": "25.10.2023"})
        self.assertIsNone(result["invoice_date"])

    def test_validate_drops_unknown_currency(self):
        from ..services import llm_extractor

        result = llm_extractor._validate_data(
            {"currency": "ZZZ"}, available_currencies=["TRY", "USD"]
        )
        self.assertIsNone(result["currency"])

    def test_validate_removes_unknown_tax_rate(self):
        from ..services import llm_extractor

        data = {
            "lines": [
                {"name": "Nakliye", "tax_rate": 18},
                {"name": "Depolama", "tax_rate": 20},
            ]
        }
        result = llm_extractor._validate_data(
            data,
            available_taxes=[
                {"id": 34, "name": "20%", "amount": 20.0, "amount_type": "percent"}
            ],
        )
        self.assertNotIn("tax_rate", result["lines"][0])
        self.assertEqual(result["lines"][1]["tax_rate"], 20)

    def test_validate_removes_unknown_tax_id(self):
        from ..services import llm_extractor

        data = {"lines": [{"name": "Nakliye", "tax_id": 999}]}
        result = llm_extractor._validate_data(
            data,
            available_taxes=[
                {"id": 34, "name": "20%", "amount": 20.0, "amount_type": "percent"}
            ],
        )
        self.assertNotIn("tax_id", result["lines"][0])


class TestAccountMoveExtraction(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {"name": "Voslo Lojistik", "is_company": True}
        )
        cls.move = cls.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": cls.partner.id,
            }
        )
        cls.connection = cls.env["ai.connection"].create(
            {
                "name": "Test Connection",
                "kind": "openai_compatible",
                "url": "http://ollama:11434/v1",
                "model": "qwen3-vl:8b",
                "temperature": 0,
            }
        )
        cls.env["ir.config_parameter"].sudo().set_param(
            "ai_document_extraction.ai_connection_id", str(cls.connection.id)
        )

    def _attach(self):
        png = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8B"
            "QDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        return self.env["ir.attachment"].create(
            {
                "name": "invoice.png",
                "datas": png,
                "mimetype": "image/png",
                "res_model": "account.move",
                "res_id": self.move.id,
            }
        )

    def test_match_partner_exact(self):
        match = self.move._match_partner("Voslo Lojistik", 85)
        self.assertEqual(match, self.partner)

    def test_match_partner_below_threshold(self):
        match = self.move._match_partner("Bilinmeyen Firma", 85)
        self.assertIsNone(match)

    def test_new_vendor_bill_defaults_invoice_date(self):
        from odoo import fields as odoo_fields

        move = self.env["account.move"].create({"move_type": "in_invoice"})
        self.assertEqual(
            move.invoice_date,
            odoo_fields.Date.context_today(self.env["account.move"]),
        )

    def test_apply_extraction(self):
        data = {
            "partner_name": "Voslo Lojistik",
            "invoice_number": "FT-123",
            "invoice_date": "2023-10-25",
            "amount_untaxed": 100.0,
            "amount_tax": 18.0,
            "amount_total": 118.0,
            "currency": "TRY",
        }
        matched = self.move._apply_extraction(data)
        self.assertEqual(self.move.partner_id, self.partner)
        self.assertEqual(self.move.ref, "FT-123")
        self.assertEqual(str(self.move.invoice_date), "2023-10-25")
        self.assertTrue(self.move.line_ids)
        self.assertEqual(self.move.ai_extracted_tax, 18.0)
        self.assertIsNotNone(matched)

    def test_apply_extraction_with_lines(self):
        data = {
            "partner_name": "Voslo Lojistik",
            "invoice_number": "FT-456",
            "amount_tax": 18.0,
            "amount_total": 118.0,
            "lines": [
                {"name": "Nakliye Hizmeti", "quantity": 1, "price_unit": 90.0},
                {"name": "Depolama", "quantity": 2, "price_unit": 5.0},
            ],
        }
        self.move._apply_extraction(data)
        line_names = [line.name for line in self.move.line_ids if line.price_subtotal]
        self.assertIn("Nakliye Hizmeti", line_names)
        self.assertIn("Depolama", line_names)

    def test_apply_sets_payment_reference_field(self):
        data = {
            "invoice_number": "FT-123",
            "payment_reference": "PAY-XYZ",
        }
        self.move._apply_extraction(data)
        self.assertEqual(self.move.ref, "FT-123")
        self.assertEqual(self.move.payment_reference, "PAY-XYZ")

    def test_apply_falls_back_to_payment_reference(self):
        data = {
            "invoice_number": None,
            "payment_reference": "9e06cda8-3e39-492f-9863-11c6b4a0ad3e",
        }
        self.move._apply_extraction(data)
        self.assertEqual(self.move.ref, "9e06cda8-3e39-492f-9863-11c6b4a0ad3e")
        self.assertEqual(
            self.move.payment_reference, "9e06cda8-3e39-492f-9863-11c6b4a0ad3e"
        )
        bodies = [message.body or "" for message in self.move.message_ids]
        self.assertTrue(any("payment reference" in body.lower() for body in bodies))

    def test_apply_no_fallback_note_when_invoice_number_present(self):
        data = {"invoice_number": "FT-123", "payment_reference": "PAY-XYZ"}
        self.move._apply_extraction(data)
        bodies = [message.body or "" for message in self.move.message_ids]
        self.assertFalse(any("payment reference" in body.lower() for body in bodies))

    def test_settings_ai_connection_link(self):
        settings = self.env["res.config.settings"].create(
            {
                "ai_connection_id": self.connection.id,
                "fuzzy_match_threshold": 90,
            }
        )
        settings.execute()
        loaded = self.env["res.config.settings"].create({})
        self.assertEqual(loaded.ai_connection_id, self.connection)
        self.assertEqual(loaded.fuzzy_match_threshold, 90)

    def test_ai_settings_includes_llm_timeout(self):
        settings = self.move._ai_settings()
        self.assertEqual(settings["llm_timeout"], 300)

    def test_ai_settings_defaults(self):
        settings = self.move._ai_settings()
        self.assertEqual(settings["api_base_url"], "https://openrouter.ai/api/v1")
        self.assertEqual(settings["api_key"], "")
        self.assertEqual(settings["model_name"], "qwen/qwen3-vl-32b-instruct")
        self.assertEqual(settings["num_ctx"], 8192)
        self.assertEqual(settings["keep_alive"], "30m")
        self.assertEqual(settings["llm_timeout"], 300)

    def test_ai_resize_caps_at_1280(self):
        from PIL import Image

        path = "/tmp/ai_resize_test.png"
        Image.new("RGB", (2000, 2600), "white").save(path)
        try:
            result = self.move._ai_resize_image(path)
            width, height = Image.open(result).size
            self.assertLessEqual(max(width, height), 1280)
        finally:
            for candidate in (path, f"{path}.resized.png"):
                if os.path.exists(candidate):
                    os.unlink(candidate)

    def test_apply_extraction_sets_currency(self):
        data = {"currency": "USD"}
        self.move._apply_extraction(data)
        self.assertEqual(self.move.currency_id.name, "USD")

    def test_apply_extraction_ignores_unknown_currency(self):
        data = {"currency": "ZZZ"}
        self.move._apply_extraction(data)
        self.assertEqual(self.move.currency_id, self.move.company_id.currency_id)

    def test_apply_extraction_applies_line_tax(self):
        tax = self.env["account.tax"].create(
            {
                "name": "AI Test 20%",
                "amount": 20.0,
                "amount_type": "percent",
                "type_tax_use": "purchase",
                "company_id": self.env.company.id,
            }
        )
        data = {
            "lines": [
                {
                    "name": "Nakliye Hizmeti",
                    "quantity": 1,
                    "price_unit": 100.0,
                    "tax_rate": 20.0,
                }
            ]
        }
        self.move._apply_extraction(data)
        line = self.move.line_ids.filtered(lambda line: line.price_subtotal)
        self.assertEqual(line.tax_ids, tax)
        self.assertEqual(self.move.amount_tax, 20.0)
        self.assertEqual(self.move.amount_total, 120.0)

    def test_apply_extraction_line_untaxed_when_tax_unknown(self):
        data = {
            "lines": [
                {
                    "name": "Nakliye Hizmeti",
                    "quantity": 1,
                    "price_unit": 100.0,
                    "tax_rate": 18.0,
                }
            ]
        }
        self.move._apply_extraction(data)
        line = self.move.line_ids.filtered(lambda line: line.price_subtotal)
        self.assertFalse(line.tax_ids)

    def test_apply_extraction_fallback_line_uses_description(self):
        data = {"amount_untaxed": 100.0, "description": "Nakliye Hizmeti"}
        self.move._apply_extraction(data)
        line = self.move.line_ids.filtered(lambda line: line.price_subtotal)
        self.assertEqual(len(line), 1)
        self.assertEqual(line.name, "Nakliye Hizmeti")
        self.assertEqual(line.price_subtotal, 100.0)

    def test_apply_extraction_never_uses_default_line_name(self):
        data = {
            "lines": [{"name": "Nakliye Hizmeti", "quantity": 1, "price_unit": 90.0}],
            "amount_untaxed": 90.0,
        }
        self.move._apply_extraction(data)
        self.assertFalse(
            self.move.line_ids.filtered(lambda line: line.name == "AI extracted amount")
        )

    def test_apply_extraction_warns_when_date_missing(self):
        self.move._apply_extraction({"lines": []})
        bodies = [message.body or "" for message in self.move.message_ids]
        self.assertTrue(any("invoice date" in body.lower() for body in bodies))

    def test_upload_image_posts_informative_message(self):
        attachment = self._attach()
        journal = self.env["account.journal"].search(
            [("type", "=", "purchase")], limit=1
        )
        records = (
            self.env["account.move"]
            .with_context(default_journal_id=journal.id)
            ._create_records_from_attachments(attachment)
        )
        move = records[0]
        bodies = [message.body or "" for message in move.message_ids]
        self.assertFalse(
            any("error while importing" in body.lower() for body in bodies)
        )
        self.assertTrue(any("Extract with AI" in body for body in bodies))

    def test_upload_non_processable_file_keeps_import_error(self):
        import base64

        attachment = self.env["ir.attachment"].create(
            {
                "name": "edifact.xml",
                "datas": base64.b64encode(b"<root/>"),
                "mimetype": "application/xml",
            }
        )
        journal = self.env["account.journal"].search(
            [("type", "=", "purchase")], limit=1
        )
        records = (
            self.env["account.move"]
            .with_context(default_journal_id=journal.id)
            ._create_records_from_attachments(attachment)
        )
        move = records[0]
        bodies = [message.body or "" for message in move.message_ids]
        self.assertTrue(any("error while importing" in body.lower() for body in bodies))

    def test_ai_is_processable_ignores_duplicate_suffix(self):
        self.assertTrue(self.move._ai_is_processable("receipt_90b5ba57.pdf (1)"))
        self.assertTrue(self.move._ai_is_processable("invoice.PNG (2)"))
        self.assertFalse(self.move._ai_is_processable("edifact.xml"))
        self.assertFalse(self.move._ai_is_processable("archive"))

    def test_upload_duplicate_suffixed_file_posts_informative_message(self):
        import base64

        attachment = self.env["ir.attachment"].create(
            {
                "name": "receipt_90b5ba57-31c0-4373-a61f-d4b84adea60e.pdf (1)",
                "datas": base64.b64encode(b"%PDF-1.4 fake receipt"),
                "mimetype": "application/pdf",
            }
        )
        journal = self.env["account.journal"].search(
            [("type", "=", "purchase")], limit=1
        )
        records = (
            self.env["account.move"]
            .with_context(default_journal_id=journal.id)
            ._create_records_from_attachments(attachment)
        )
        move = records[0]
        bodies = [message.body or "" for message in move.message_ids]
        self.assertFalse(
            any("error while importing" in body.lower() for body in bodies)
        )
        self.assertTrue(any("Extract with AI" in body for body in bodies))

    def test_ai_prepare_image_recognizes_duplicate_suffixed_pdf(self):
        import base64
        import io

        from PIL import Image

        png = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8B"
            "QDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        attachment = self.env["ir.attachment"].create(
            {
                "name": "receipt_90b5ba57-31c0-4373-a61f-d4b84adea60e.pdf (1)",
                "datas": base64.b64encode(b"%PDF-1.4 fake receipt"),
                "mimetype": "application/pdf",
            }
        )
        with mock.patch("pdf2image.convert_from_path") as mock_convert:
            mock_convert.return_value = [Image.open(io.BytesIO(base64.b64decode(png)))]
            path = self.move._ai_prepare_image(attachment)
        self.assertTrue(path.endswith(".png"))
        mock_convert.assert_called_once()

    def test_action_extract_with_ai_allows_customer_invoice(self):
        move = self.env["account.move"].create({"move_type": "out_invoice"})
        self.env["ir.attachment"].create(
            {
                "name": "invoice.png",
                "datas": (
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
                    "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
                ),
                "mimetype": "image/png",
                "res_model": "account.move",
                "res_id": move.id,
            }
        )
        with mock.patch.object(type(move), "with_delay", return_value=mock.Mock()):
            move.action_extract_with_ai()
        self.assertEqual(move.ai_extraction_state, "processing")

    def test_job_stores_processed_image(self):
        import base64

        from ..services import llm_extractor

        png_path = "/tmp/ai_processed_test.png"
        png = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8B"
            "QDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        with open(png_path, "wb") as handle:
            handle.write(base64.b64decode(png))
        attachment = self._attach()
        with mock.patch.object(
            llm_extractor,
            "extract_invoice_data_from_image",
            return_value={"partner_name": "Voslo Lojistik", "lines": []},
        ):
            self.move._extract_with_ai_job(attachment.id)
        if os.path.exists(png_path):
            os.unlink(png_path)
        stored = self.env["ir.attachment"].search(
            [
                ("res_model", "=", "account.move"),
                ("res_id", "=", self.move.id),
                ("name", "like", "-ai-processed.png"),
            ]
        )
        self.assertTrue(stored)
        self.assertEqual(stored.mimetype, "image/png")

    def test_job_happy_path(self):
        from ..services import llm_extractor

        attachment = self._attach()
        with mock.patch.object(
            llm_extractor,
            "extract_invoice_data_from_image",
            return_value={
                "partner_name": "Voslo Lojistik",
                "invoice_number": "FT-123",
                "invoice_date": "2023-10-25",
                "amount_untaxed": 100.0,
                "amount_tax": 18.0,
                "amount_total": 118.0,
                "currency": "TRY",
            },
        ):
            self.move._extract_with_ai_job(attachment.id)
        self.assertEqual(self.move.ai_extraction_state, "done")
        self.assertEqual(self.move.ref, "FT-123")
        self.assertIn("partner_name", self.move.ai_raw_extraction)

    def test_job_error_path(self):
        from ..services import llm_extractor

        attachment = self._attach()
        with mock.patch.object(
            llm_extractor,
            "extract_invoice_data_from_image",
            side_effect=RuntimeError("boom"),
        ):
            self.move._extract_with_ai_job(attachment.id)
        self.assertEqual(self.move.ai_extraction_state, "error")

    def test_job_notifies_bus_on_done(self):
        from ..services import llm_extractor

        attachment = self._attach()
        with mock.patch.object(
            llm_extractor,
            "extract_invoice_data_from_image",
            return_value={
                "partner_name": "Voslo Lojistik",
                "invoice_number": "FT-123",
                "invoice_date": "2023-10-25",
                "amount_untaxed": 100.0,
                "amount_tax": 18.0,
                "amount_total": 118.0,
            },
        ):
            with mock.patch.object(
                type(self.env["bus.bus"]), "_sendone"
            ) as mock_sendone:
                self.move._extract_with_ai_job(attachment.id)
        mock_sendone.assert_called_once_with(
            f"ai_document_extraction.move.{self.move.id}",
            "ai_document_extraction",
            {"move_id": self.move.id, "state": "done"},
        )

    def test_job_notifies_bus_on_error(self):
        from ..services import llm_extractor

        attachment = self._attach()
        with mock.patch.object(
            llm_extractor,
            "extract_invoice_data_from_image",
            side_effect=RuntimeError("boom"),
        ):
            with mock.patch.object(
                type(self.env["bus.bus"]), "_sendone"
            ) as mock_sendone:
                self.move._extract_with_ai_job(attachment.id)
        mock_sendone.assert_called_once_with(
            f"ai_document_extraction.move.{self.move.id}",
            "ai_document_extraction",
            {"move_id": self.move.id, "state": "error"},
        )

    def test_apply_extraction_keeps_partner_if_not_matched(self):
        data = {
            "partner_name": "Var Olmayan Firma",
            "invoice_number": "FT-999",
        }
        self.move._apply_extraction(data)
        self.assertEqual(self.move.partner_id, self.partner)
        self.assertEqual(self.move.ref, "FT-999")

    def test_action_extract_with_ai_requires_draft(self):
        from odoo.exceptions import UserError

        self.move.invoice_date = "2023-10-25"
        account = self.env["account.account"].search(
            [("internal_group", "=", "expense")], limit=1
        )
        self.move.write(
            {
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Test",
                            "account_id": account.id,
                            "quantity": 1,
                            "price_unit": 10.0,
                        },
                    )
                ]
            }
        )
        self.move.with_context(skip_invoice_sync=True).action_post()
        with self.assertRaises(UserError):
            self.move.action_extract_with_ai()

    def test_ai_buttons_hidden_on_non_draft(self):
        from lxml import etree

        view = self.env.ref("ai_document_extraction.account_move_form_ai_extraction")
        arch = etree.fromstring(view.arch)
        buttons = {
            button.get("name"): button.get("invisible", "")
            for button in arch.iter("button")
            if button.get("name")
            in ("action_extract_with_ai", "action_review_extraction")
        }
        self.assertEqual(
            set(buttons),
            {"action_extract_with_ai", "action_review_extraction"},
        )
        for name, invisible in buttons.items():
            self.assertIn(
                "state != 'draft'",
                invisible,
                f"{name} should be hidden on non-draft moves",
            )

    def test_action_extract_with_ai_requires_vendor_bill(self):
        from odoo.exceptions import UserError

        move = self.env["account.move"].create({"move_type": "out_invoice"})
        with self.assertRaises(UserError):
            move.action_extract_with_ai()

    def test_action_extract_with_ai_requires_attachment(self):
        from odoo.exceptions import UserError

        move = self.env["account.move"].create({"move_type": "in_invoice"})
        with self.assertRaises(UserError):
            move.action_extract_with_ai()

    def test_action_extract_with_ai_enqueues(self):
        move = self.env["account.move"].create({"move_type": "in_invoice"})
        attachment = self.env["ir.attachment"].create(
            {
                "name": "invoice.png",
                "datas": (
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
                    "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
                ),
                "mimetype": "image/png",
                "res_model": "account.move",
                "res_id": move.id,
            }
        )
        with mock.patch.object(
            type(move), "with_delay", return_value=mock.Mock()
        ) as delay_mock:
            move.action_extract_with_ai()
        self.assertEqual(move.ai_extraction_state, "processing")
        delay_mock.return_value._extract_with_ai_job.assert_called_once_with(
            attachment.id
        )


class TestExtractionWizard(TransactionCase):
    def test_wizard_apply_partner(self):
        move = self.env["account.move"].create({"move_type": "in_invoice"})
        partner = self.env["res.partner"].create(
            {"name": "Yeni Firma", "is_company": True}
        )
        wizard = self.env["extraction.wizard"].create(
            {
                "move_id": move.id,
                "extracted_partner_name": "Yeni Firma",
                "partner_id": partner.id,
            }
        )
        result = wizard.action_apply()
        self.assertEqual(move.partner_id, partner)
        self.assertEqual(move.ai_extraction_state, "done")
        self.assertEqual(result["res_id"], move.id)

    def test_wizard_apply_ignores_non_draft(self):
        partner = self.env["res.partner"].create({"name": "Firma", "is_company": True})
        move = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": partner.id,
            }
        )
        move.invoice_date = "2023-10-25"
        account = self.env["account.account"].search(
            [("internal_group", "=", "expense")], limit=1
        )
        move.write(
            {
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "Test",
                            "account_id": account.id,
                            "quantity": 1,
                            "price_unit": 10.0,
                        },
                    )
                ]
            }
        )
        move.with_context(skip_invoice_sync=True).action_post()
        wizard = self.env["extraction.wizard"].create(
            {
                "move_id": move.id,
                "partner_id": partner.id,
            }
        )
        result = wizard.action_apply()
        self.assertEqual(move.partner_id.id, partner.id)
        # move is posted; do not change its state
        self.assertEqual(result["type"], "ir.actions.act_window_close")

    def test_wizard_apply_empty_partner_keeps_existing(self):
        move = self.env["account.move"].create({"move_type": "in_invoice"})
        existing = self.env["res.partner"].create(
            {"name": "Mevcut Firma", "is_company": True}
        )
        move.partner_id = existing.id
        wizard = self.env["extraction.wizard"].create(
            {
                "move_id": move.id,
                "extracted_partner_name": "Bilinmeyen",
            }
        )
        wizard.action_apply()
        self.assertEqual(move.partner_id, existing)
        self.assertEqual(move.ai_extraction_state, "done")

    def test_action_review_extraction_creates_wizard(self):
        move = self.env["account.move"].create({"move_type": "in_invoice"})
        partner = self.env["res.partner"].create(
            {"name": "Voslo Lojistik", "is_company": True}
        )
        move.write(
            {
                "partner_id": partner.id,
                "ai_raw_extraction": '{"partner_name": "Voslo Lojistik"}',
            }
        )
        result = move.action_review_extraction()
        self.assertEqual(result["res_model"], "extraction.wizard")
        self.assertEqual(result["target"], "new")
        wizard = self.env["extraction.wizard"].browse(result["res_id"])
        self.assertEqual(wizard.move_id, move)
        self.assertEqual(wizard.extracted_partner_name, "Voslo Lojistik")
        self.assertEqual(wizard.partner_id, partner)


class TestAiConnection(TransactionCase):
    def test_openai_compatible_kind_builds_client(self):
        connection = self.env["ai.connection"].create(
            {
                "name": "OpenRouter",
                "kind": "openai_compatible",
                "url": "https://openrouter.ai/api/v1",
                "model": "qwen/qwen3-vl-32b-instruct",
            }
        )
        client = connection._get_client_openai_compatible(None)
        self.assertEqual(client.url, "https://openrouter.ai/api/v1")
        self.assertEqual(client.model, "qwen/qwen3-vl-32b-instruct")
        self.assertEqual(client.api_key, "")


class TestAiOpenAICompatibleClient(TransactionCase):
    def _client(self, **kw):
        defaults = {
            "url": "https://openrouter.ai/api/v1",
            "model": "qwen/qwen3-vl-32b-instruct",
        }
        defaults.update(kw)
        from ..services.ai_openai_compatible_client import (
            AiOpenAICompatibleClient,
        )

        return AiOpenAICompatibleClient(**defaults)

    def _mock_response(self, content):
        response = mock.Mock()
        response.status_code = 200
        response.json.return_value = {"choices": [{"message": {"content": content}}]}
        return response

    def test_handle_message_posts_openai_payload(self):
        from ..services import ai_openai_compatible_client as client_mod

        response = self._mock_response('{"ok": 1}')
        messages = [{"role": "user", "content": "hello"}]
        with mock.patch.object(
            client_mod.requests, "post", return_value=response
        ) as post_mock:
            result = self._client().handle_message(messages, temperature=0)
        self.assertEqual(result["message"]["content"], '{"ok": 1}')
        self.assertEqual(result["tool_calls"], [])
        payload = post_mock.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "qwen/qwen3-vl-32b-instruct")
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["messages"], messages)
        self.assertNotIn("options", payload)

    def test_handle_message_sends_api_key(self):
        from ..services import ai_openai_compatible_client as client_mod

        response = self._mock_response('{"ok": 1}')
        with mock.patch.object(
            client_mod.requests, "post", return_value=response
        ) as post_mock:
            self._client(api_key="secret").handle_message(
                [{"role": "user", "content": "hi"}]
            )
        self.assertEqual(
            post_mock.call_args.kwargs["headers"]["Authorization"], "Bearer secret"
        )

    def test_handle_message_adds_ollama_options(self):
        from ..services import ai_openai_compatible_client as client_mod

        response = self._mock_response('{"ok": 1}')
        with mock.patch.object(
            client_mod.requests, "post", return_value=response
        ) as post_mock:
            self._client(
                url="http://ollama:11434/v1", num_ctx=32768, keep_alive="30m"
            ).handle_message([{"role": "user", "content": "hi"}])
        payload = post_mock.call_args.kwargs["json"]
        self.assertEqual(payload["options"], {"num_ctx": 32768})
        self.assertEqual(payload["keep_alive"], "30m")

    def test_handle_message_omits_ollama_options_on_cloud(self):
        from ..services import ai_openai_compatible_client as client_mod

        response = self._mock_response('{"ok": 1}')
        with mock.patch.object(
            client_mod.requests, "post", return_value=response
        ) as post_mock:
            self._client(num_ctx=8192, keep_alive="30m").handle_message(
                [{"role": "user", "content": "hi"}]
            )
        payload = post_mock.call_args.kwargs["json"]
        self.assertNotIn("options", payload)
        self.assertNotIn("keep_alive", payload)

    def test_handle_message_retries_once_on_empty_content(self):
        from ..services import ai_openai_compatible_client as client_mod

        with mock.patch.object(
            client_mod.requests,
            "post",
            side_effect=[self._mock_response(""), self._mock_response('{"ok": 1}')],
        ) as post_mock:
            result = self._client().handle_message([{"role": "user", "content": "hi"}])
        self.assertEqual(post_mock.call_count, 2)
        self.assertEqual(result["message"]["content"], '{"ok": 1}')

    def test_handle_message_raises_after_empty_retries(self):
        from ..services import ai_openai_compatible_client as client_mod

        with mock.patch.object(
            client_mod.requests, "post", return_value=self._mock_response("")
        ):
            with self.assertRaises(ValueError):
                self._client().handle_message([{"role": "user", "content": "hi"}])

    def test_handle_message_passes_timeout(self):
        from ..services import ai_openai_compatible_client as client_mod

        response = self._mock_response('{"ok": 1}')
        with mock.patch.object(
            client_mod.requests, "post", return_value=response
        ) as post_mock:
            self._client(timeout=300).handle_message(
                [{"role": "user", "content": "hi"}]
            )
        self.assertEqual(post_mock.call_args.kwargs["timeout"], 300)
