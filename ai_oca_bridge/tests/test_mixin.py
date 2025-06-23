# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo_test_helper import FakeModelLoader

from odoo.exceptions import ValidationError
from odoo.tests.common import Form, TransactionCase


class TestBridge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Load fake models ->/
        cls.loader = FakeModelLoader(cls.env, cls.__module__)
        cls.loader.backup_registry()
        from .fake_models import BridgeTest

        cls.loader.update_registry((BridgeTest,))
        cls.bridge = cls.env["ai.bridge"].create(
            {
                "name": "Test Bridge",
                "model_id": cls.env["ir.model"]._get_id("bridge.test"),
                "url": "https://example.com/api",
                "auth_type": "none",
                "usage": "none",
            }
        )

    @classmethod
    def tearDownClass(cls):
        cls.loader.restore_registry()
        super().tearDownClass()

    def test_bridge_thread_creation(self):
        self.bridge.write({"usage": "ai_thread_create"})
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"result": "success"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge.id)]
                ),
            )
            # Create a test record
            record = self.env["bridge.test"].create({"name": "Test Record"})
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge.id)]
                ),
            )
            mock_post.assert_called_once()
            record.write({"name": "Updated Record"})
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge.id)]
                ),
            )
            record.unlink()
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge.id)]
                ),
            )
            mock_post.assert_called_once()

    def test_bridge_thread_write(self):
        self.bridge.write({"usage": "ai_thread_write"})
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"result": "success"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge.id)]
                ),
            )
            # Create a test record
            record = self.env["bridge.test"].create({"name": "Test Record"})
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge.id)]
                ),
            )
            record.write({"name": "Updated Record"})
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge.id)]
                ),
            )
            record.unlink()
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge.id)]
                ),
            )
            mock_post.assert_called_once()

    def test_bridge_thread_unlink(self):
        self.assertNotEqual(self.bridge.payload_type, "none")
        with Form(self.bridge) as bridge_form:
            bridge_form.usage = "ai_thread_unlink"
        self.assertEqual(self.bridge.payload_type, "none")
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"result": "success"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge.id)]
                ),
            )
            # Create a test record
            record = self.env["bridge.test"].create({"name": "Test Record"})
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge.id)]
                ),
            )
            record.write({"name": "Updated Record"})
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge.id)]
                ),
            )
            record.unlink()
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge.id)]
                ),
            )
            mock_post.assert_called_once()

    def test_bridge_thread_unlink_constrains(self):
        self.assertNotEqual(self.bridge.payload_type, "none")
        with Form(self.bridge) as bridge_form:
            bridge_form.usage = "ai_thread_unlink"
        self.assertEqual(self.bridge.payload_type, "none")
        with self.assertRaises(ValidationError):
            self.bridge.payload_type = "record"

    def test_bridge_model_search(self):
        models = self.env["ir.model"].search([("ai_usage", "=", "thread")])
        model = self.env["ir.model"]._get_id("bridge.test")
        self.assertTrue(models)
        self.assertIn(self.env.ref("base.model_res_partner"), models)
        self.assertNotIn(model, models.ids)
        models = self.env["ir.model"].search([("ai_usage", "=", "ai_thread_create")])
        self.assertTrue(models)
        self.assertNotIn(self.env.ref("base.model_res_partner"), models)
        self.assertIn(model, models.ids)
        models = self.env["ir.model"].search([("ai_usage", "=", "none")])
        self.assertTrue(models)
        self.assertIn(self.env.ref("base.model_res_partner"), models)
        self.assertIn(model, models.ids)

    def test_bridge_model_required(self):
        self.assertFalse(self.bridge.model_required)
        self.bridge.usage = "ai_thread_create"
        self.assertTrue(self.bridge.model_required)
        self.bridge.usage = "thread"
        self.assertTrue(self.bridge.model_required)
