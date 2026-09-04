# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo_test_helper import FakeModelLoader

from odoo.tests import TransactionCase

from odoo.addons.field_vector.fields import VectorValue


class TestVectorCompute(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Load fake models ->/
        cls.loader = FakeModelLoader(cls.env, cls.__module__)
        cls.loader.backup_registry()
        from .fake_models_compute import VectorFakeModel

        cls.loader.update_registry((VectorFakeModel,))

        cls.addClassCleanup(cls.loader.restore_registry)

        cls.vector_model = cls.env["vector.fake.model"]

    def test_compute(self):
        field_config = self.env["ir.model.field.vector"].create(
            {
                "field_id": self.env["ir.model.fields"]
                .search(
                    [
                        ("model", "=", "vector.fake.model"),
                        ("name", "=", "description_vector"),
                    ],
                    limit=1,
                )
                .id,
                "dimensions": 20,
                "vector_method": "openai",
            }
        )
        field_config.update_column()
        self.assertTrue(field_config.compute)
        with mock.patch("openai.OpenAI") as mock_openai:
            mock_embedding = mock.MagicMock()
            mock_embedding.embedding = [0.5] * 20

            mock_response = mock.MagicMock()
            mock_response.data = [mock_embedding]

            mock_openai.return_value.embeddings.create.return_value = mock_response
            records = self.env["vector.fake.model"].create(
                [
                    {
                        "name": "Test_01",
                    },
                    {
                        "name": "Test_02",
                    },
                ]
            )
            records.flush_recordset()
        self.assertEqual(
            VectorValue([0.5] * 20),
            self.env["vector.fake.model"]
            .search([("name", "=", "Test_01")], limit=1)
            .description_vector,
        )
        self.assertEqual(
            VectorValue([0.5] * 20),
            self.env["vector.fake.model"]
            .search([("name", "=", "Test_02")], limit=1)
            .description_vector,
        )
        with mock.patch("openai.OpenAI") as mock_openai:
            mock_embedding = mock.MagicMock()
            mock_embedding.embedding = [0.3] * 20

            mock_response = mock.MagicMock()
            mock_response.data = [mock_embedding]
            mock_openai.return_value.embeddings.create.return_value = mock_response
            field_config.compute_values()
            records.flush_recordset()
        self.assertEqual(
            VectorValue([0.3] * 20),
            self.env["vector.fake.model"]
            .search([("name", "=", "Test_01")], limit=1)
            .description_vector,
        )
        self.assertEqual(
            VectorValue([0.3] * 20),
            self.env["vector.fake.model"]
            .search([("name", "=", "Test_02")], limit=1)
            .description_vector,
        )
