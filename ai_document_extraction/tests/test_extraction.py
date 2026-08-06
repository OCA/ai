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
