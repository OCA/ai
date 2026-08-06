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
        result = preprocess_image(source)
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
                        "content": '{"partner_name": "Voslo", "amount_total": 118.0}'
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
        self.assertEqual(data["partner_name"], "Voslo")
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
