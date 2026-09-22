# Copyright 2026 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo_test_helper import FakeModelLoader

from odoo.exceptions import UserError
from odoo.tests import TransactionCase

from odoo.addons.field_vector.fields import VectorValue


class TestVector(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Load fake models ->/
        cls.loader = FakeModelLoader(cls.env, cls.__module__)
        cls.loader.backup_registry()
        from .fake_models import VectorFakeModel

        cls.loader.update_registry((VectorFakeModel,))

        cls.addClassCleanup(cls.loader.restore_registry)

        cls.vector_model = cls.env["vector.fake.model"]
        cls.partner_01 = cls.env["res.partner"].create({"name": "Partner 01"})
        cls.partner_02 = cls.env["res.partner"].create({"name": "Partner 02"})

    def test_vector(self):
        vector_field = self.vector_model._fields["description_vector"]
        self.assertEqual(
            10,
            vector_field.get_current_vector_size(
                self.env.cr, self.vector_model._table, vector_field.name
            ),
        )
        self.assertEqual(10, vector_field.vector_dimensions(self.vector_model))
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
        self.assertEqual(
            10,
            vector_field.get_current_vector_size(
                self.env.cr, self.vector_model._table, vector_field.name
            ),
        )
        self.assertEqual(20, vector_field.vector_dimensions(self.vector_model))
        field_config.update_column()
        self.assertEqual(
            20,
            vector_field.get_current_vector_size(
                self.env.cr, self.vector_model._table, vector_field.name
            ),
        )
        self.assertEqual(20, vector_field.vector_dimensions(self.vector_model))

    def test_vector_encoding(self):
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
        record_01 = self.vector_model.create({"name": "Test"})
        with mock.patch("openai.OpenAI") as mock_openai:
            mock_embedding = mock.MagicMock()
            mock_embedding.embedding = [0.5] * 20

            mock_response = mock.MagicMock()
            mock_response.data = [mock_embedding]

            mock_openai.return_value.embeddings.create.return_value = mock_response
            record_01.description_vector = record_01._encode_vector(
                "description_vector", "MY OWN QUERY"
            )[0]
        self.assertEqual(record_01.description_vector, VectorValue([0.5] * 20))
        record_02 = self.vector_model.create({"name": "Test"})
        with mock.patch("openai.OpenAI") as mock_openai:
            mock_embedding = mock.MagicMock()
            mock_embedding.embedding = [0.2] * 20

            mock_response = mock.MagicMock()
            mock_response.data = [mock_embedding]

            mock_openai.return_value.embeddings.create.return_value = mock_response
            record_02.description_vector = record_02._encode_vector(
                "description_vector", "MY OWN QUERY"
            )[0]
        self.assertEqual(record_02.description_vector, VectorValue([0.2] * 20))
        record_03 = self.vector_model.create({"name": "Test"})
        with mock.patch("openai.OpenAI") as mock_openai:
            mock_embedding = mock.MagicMock()
            mock_embedding.embedding = [0.6] * 20

            mock_response = mock.MagicMock()
            mock_response.data = [mock_embedding]

            mock_openai.return_value.embeddings.create.return_value = mock_response
            record_03.description_vector = record_03._encode_vector(
                "description_vector", "MY OWN QUERY"
            )[0]
        self.assertEqual(record_03.description_vector, VectorValue([0.6] * 20))

    def test_search(self):
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
        record_01 = self.vector_model.create(
            {
                "name": "Test",
                "description_vector": VectorValue([0.2] * 20),
                "partner_id": self.partner_01.id,
            }
        )
        record_02 = self.vector_model.create(
            {
                "name": "Test",
                "description_vector": VectorValue([0.5] * 20),
                "partner_id": self.partner_02.id,
            }
        )
        record_03 = self.vector_model.create(
            {
                "name": "Test",
                "description_vector": VectorValue([0.6] * 20),
                "partner_id": self.partner_01.id,
            }
        )
        with mock.patch("openai.OpenAI") as mock_openai:
            mock_embedding = mock.MagicMock()
            mock_embedding.embedding = [0.45] * 20

            mock_response = mock.MagicMock()
            mock_response.data = [mock_embedding]

            mock_openai.return_value.embeddings.create.return_value = mock_response
            results = self.vector_model.search_vector(
                "description_vector", "MY OWN QUERY"
            )
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].id, record_02.id)
        self.assertEqual(results[1].id, record_03.id)
        self.assertEqual(results[2].id, record_01.id)
        with mock.patch("openai.OpenAI") as mock_openai:
            mock_embedding = mock.MagicMock()
            mock_embedding.embedding = [0.45] * 20

            mock_response = mock.MagicMock()
            mock_response.data = [mock_embedding]

            mock_openai.return_value.embeddings.create.return_value = mock_response
            results = self.vector_model.search_vector(
                "description_vector",
                "MY OWN QUERY",
                domain=[("partner_id", "=", self.partner_01.id)],
            )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].id, record_03.id)
        self.assertEqual(results[1].id, record_01.id)

    def test_search_aggregated(self):
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
        self.vector_model.create(
            [
                {
                    "name": "Test",
                    "description_vector": VectorValue([0.2] * 20),
                    "partner_id": self.partner_01.id,
                },
                {
                    "name": "Test",
                    "description_vector": VectorValue([0.5] * 20),
                    "partner_id": self.partner_02.id,
                },
                {
                    "name": "Test",
                    "description_vector": VectorValue([0.6] * 20),
                    "partner_id": self.partner_01.id,
                },
            ]
        )
        with mock.patch("openai.OpenAI") as mock_openai:
            mock_embedding = mock.MagicMock()
            mock_embedding.embedding = [0.56] * 20

            mock_response = mock.MagicMock()
            mock_response.data = [mock_embedding]

            mock_openai.return_value.embeddings.create.return_value = mock_response
            results = self.vector_model.search_vector_grouped(
                "description_vector", "MY OWN QUERY", "partner_id"
            )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].id, self.partner_01.id)
        self.assertEqual(results[1].id, self.partner_02.id)
        with mock.patch("openai.OpenAI") as mock_openai:
            mock_embedding = mock.MagicMock()
            mock_embedding.embedding = [0.53] * 20

            mock_response = mock.MagicMock()
            mock_response.data = [mock_embedding]

            mock_openai.return_value.embeddings.create.return_value = mock_response
            results = self.vector_model.search_vector_grouped(
                "description_vector", "MY OWN QUERY", "partner_id"
            )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].id, self.partner_02.id)
        self.assertEqual(results[1].id, self.partner_01.id)

    def test_aggregated_wrong_field(self):
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
        with self.assertRaises(UserError):
            self.vector_model.search_vector_grouped(
                "description_vector", "MY OWN QUERY", "name"
            )

    def test_aggregated_wrong_base_field(self):
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
        with self.assertRaises(UserError):
            self.vector_model.search_vector_grouped(
                "name", "MY OWN QUERY", "partner_id"
            )

    def test_wrong_base_field(self):
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
        with self.assertRaises(UserError):
            self.vector_model.search_vector(
                "name",
                "MY OWN QUERY",
            )

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
        self.assertFalse(field_config.compute)
