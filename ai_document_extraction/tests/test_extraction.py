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
        from odoo.addons.ai_document_extraction.services.image_preprocessor import (
            preprocess_image,
        )

        source = self._sample_image()
        result = preprocess_image(source)
        try:
            self.assertTrue(os.path.exists(result))
            self.assertTrue(result.endswith(".png"))
        finally:
            os.unlink(result)
