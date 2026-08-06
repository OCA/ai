# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import os

from odoo.tests import TransactionCase


class TestImagePreprocessor(TransactionCase):
    def _sample_image(self):
        import base64

        png = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8B"
            "QDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        path = "/tmp/test_sample.png"
        with open(path, "wb") as handle:
            handle.write(base64.b64decode(png))
        return path

    def test_preprocess_returns_file(self):
        from ..services.image_preprocessor import preprocess_image

        source = self._sample_image()
        try:
            result = preprocess_image(source)
        except ImportError:
            # cv2 (transitively pulled by paddleocr) may be unimportable in
            # some environments, e.g. OCA CI images without libGL.
            self.skipTest("OpenCV (cv2) not importable")
        try:
            self.assertTrue(os.path.exists(result))
            self.assertTrue(result.endswith(".png"))
        finally:
            os.unlink(result)


class TestOcrEngine(TransactionCase):
    def test_layout_tags(self):
        from unittest import mock

        from ..services import ocr_engine

        def fake_ocr(image_path, cls=True):
            return [
                [
                    ([(0, 10), (100, 10), (100, 30), (0, 30)], ("voslo", 0.99)),
                    (
                        [(0, 300), (100, 300), (100, 320), (0, 320)],
                        ("Invoice No: 123", 0.99),
                    ),
                    (
                        [(0, 650), (100, 650), (100, 670), (0, 670)],
                        ("page 1 of 1", 0.99),
                    ),
                ]
            ]

        with mock.patch.object(
            ocr_engine, "_get_ocr", return_value=mock.Mock(ocr=fake_ocr)
        ):
            result = ocr_engine.extract_text_with_layout(
                "/tmp/fake.png", image_height=700
            )
        self.assertIn("[HEADER] voslo", result)
        self.assertIn("[BODY] Invoice No: 123", result)
        self.assertIn("[FOOTER] page 1 of 1", result)

    def test_get_ocr_caches_instance_per_language(self):
        import sys
        from unittest import mock

        from ..services import ocr_engine

        class FakePaddle:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        fake_module = mock.Mock()
        fake_module.PaddleOCR = FakePaddle
        with mock.patch.dict(sys.modules, {"paddleocr": fake_module}):
            ocr_engine._thread_local.ocr = None
            ocr_engine._thread_local.ocr_lang = None
            first = ocr_engine._get_ocr("tur+eng")
            second = ocr_engine._get_ocr("tur+eng")
            self.assertIs(first, second)
            self.assertEqual(first.kwargs["lang"], "latin")
            other = ocr_engine._get_ocr("eng")
            self.assertIsNot(first, other)
            self.assertEqual(other.kwargs["lang"], "en")


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

    def test_extract_invoice_data_posts_and_parses(self):
        from unittest import mock

        from ..services import llm_extractor

        response = mock.Mock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"partner_name": "Voslo Lojistik A.S.", '
                        '"amount_total": 118.0}'
                    }
                }
            ]
        }
        with mock.patch.object(
            llm_extractor.requests, "post", return_value=response
        ) as post_mock:
            data = llm_extractor.extract_invoice_data(
                "[BODY] Invoice No: 1",
                "http://ollama:11434/v1",
                "qwen3:4b",
            )
        self.assertEqual(data["partner_name"], "Voslo Lojistik A.S.")
        post_mock.assert_called_once()
        payload = post_mock.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "qwen3:4b")
        self.assertEqual(payload["temperature"], 0)
        self.assertNotIn("Authorization", post_mock.call_args.kwargs["headers"])

    def test_extract_invoice_data_sends_api_key(self):
        from unittest import mock

        from ..services import llm_extractor

        response = mock.Mock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": '{"invoice_number": "X"}'}}]
        }
        with mock.patch.object(
            llm_extractor.requests, "post", return_value=response
        ) as post_mock:
            llm_extractor.extract_invoice_data(
                "text", "http://host:11434/v1", "m", api_key="secret"
            )
        self.assertEqual(
            post_mock.call_args.kwargs["headers"]["Authorization"],
            "Bearer secret",
        )

    def test_extract_invoice_data_sends_available_context(self):
        from unittest import mock

        from ..services import llm_extractor

        response = mock.Mock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [
                {"message": {"content": '{"partner_name": "Voslo", "lines": []}'}}
            ]
        }
        with mock.patch.object(
            llm_extractor.requests, "post", return_value=response
        ) as post_mock:
            llm_extractor.extract_invoice_data(
                "[BODY] x",
                "http://ollama:11434/v1",
                "qwen3:4b",
                available_taxes=[{"id": 34, "name": "20%", "amount": 20.0}],
                available_currencies=["TRY", "USD"],
            )
        user_content = post_mock.call_args.kwargs["json"]["messages"][1]["content"]
        self.assertIn("Available taxes", user_content)
        self.assertIn("20%", user_content)
        self.assertIn("Available currencies", user_content)
        self.assertIn("USD", user_content)

    def test_validate_rejects_hash_invoice_number(self):
        from ..services import llm_extractor

        data = {
            "invoice_number": "2054148b703b43e690b244ff544d2a9f",
            "partner_name": "VOSLO LOJISTIK A.S.",
            "invoice_date": "2023-10-25",
        }
        result = llm_extractor._validate_data(data)
        self.assertIsNone(result["invoice_number"])

    def test_validate_rejects_url_invoice_number(self):
        from ..services import llm_extractor

        result = llm_extractor._validate_data(
            {"invoice_number": "https://files.example.com/invoice.pdf"}
        )
        self.assertIsNone(result["invoice_number"])

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

    def test_validate_removes_unknown_tax_id(self):
        from ..services import llm_extractor

        data = {
            "lines": [
                {"name": "Nakliye", "tax_id": 999},
                {"name": "Depolama", "tax_id": 34},
            ]
        }
        result = llm_extractor._validate_data(data, available_tax_ids={34})
        self.assertNotIn("tax_id", result["lines"][0])
        self.assertEqual(result["lines"][1]["tax_id"], 34)


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

    def test_apply_extraction_sets_currency(self):
        data = {"currency": "USD"}
        self.move._apply_extraction(data)
        self.assertEqual(self.move.currency_id.name, "USD")

    def test_apply_extraction_ignores_unknown_currency(self):
        data = {"currency": "ZZZ"}
        self.move._apply_extraction(data)
        self.assertEqual(self.move.currency_id, self.move.company_id.currency_id)

    def test_apply_extraction_applies_line_tax(self):
        tax = self.env["account.tax"].search(
            [
                ("type_tax_use", "=", "purchase"),
                ("amount", "=", 20.0),
                ("amount_type", "=", "percent"),
            ],
            limit=1,
        )
        self.assertTrue(tax)
        data = {
            "lines": [
                {
                    "name": "Nakliye Hizmeti",
                    "quantity": 1,
                    "price_unit": 100.0,
                    "tax_id": tax.id,
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
                    "tax_id": 999,
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

    def test_action_extract_with_ai_allows_customer_invoice(self):
        from unittest import mock

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
        from unittest import mock

        from ..services import image_preprocessor, llm_extractor, ocr_engine

        png_path = "/tmp/ai_processed_test.png"
        png = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8B"
            "QDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        with open(png_path, "wb") as handle:
            handle.write(base64.b64decode(png))
        attachment = self._attach()
        with (
            mock.patch.object(
                image_preprocessor,
                "preprocess_image",
                return_value=png_path,
            ),
            mock.patch.object(
                ocr_engine,
                "extract_text_with_layout",
                return_value="[BODY] Voslo Lojistik",
            ),
            mock.patch.object(
                llm_extractor,
                "extract_invoice_data",
                return_value={"partner_name": "Voslo Lojistik", "lines": []},
            ),
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
        from unittest import mock

        from ..services import image_preprocessor, llm_extractor, ocr_engine

        attachment = self._attach()
        with (
            mock.patch.object(
                image_preprocessor,
                "preprocess_image",
                return_value="/tmp/pp.png",
            ),
            mock.patch.object(
                ocr_engine,
                "extract_text_with_layout",
                return_value="[BODY] Voslo Lojistik\n[BODY] Invoice No: FT-123",
            ),
            mock.patch.object(
                llm_extractor,
                "extract_invoice_data",
                return_value={
                    "partner_name": "Voslo Lojistik",
                    "invoice_number": "FT-123",
                    "invoice_date": "2023-10-25",
                    "amount_untaxed": 100.0,
                    "amount_tax": 18.0,
                    "amount_total": 118.0,
                    "currency": "TRY",
                },
            ),
        ):
            self.move._extract_with_ai_job(attachment.id)
        self.assertEqual(self.move.ai_extraction_state, "done")
        self.assertEqual(self.move.ref, "FT-123")
        self.assertIn("partner_name", self.move.ai_raw_extraction)

    def test_job_error_path(self):
        from unittest import mock

        from ..services import image_preprocessor, llm_extractor, ocr_engine

        attachment = self._attach()
        with (
            mock.patch.object(
                image_preprocessor,
                "preprocess_image",
                return_value="/tmp/pp.png",
            ),
            mock.patch.object(
                ocr_engine,
                "extract_text_with_layout",
                return_value="[BODY] x",
            ),
            mock.patch.object(
                llm_extractor,
                "extract_invoice_data",
                side_effect=RuntimeError("boom"),
            ),
        ):
            self.move._extract_with_ai_job(attachment.id)
        self.assertEqual(self.move.ai_extraction_state, "error")

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
        from unittest import mock

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
