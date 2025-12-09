# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo_test_helper import FakeModelLoader

from odoo.exceptions import ValidationError
from odoo.tests import new_test_user
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
        cls.user = new_test_user(
            cls.env,
            login="bridge_user",
            groups="base.group_user",
        )
        cls.portal_user = new_test_user(
            cls.env,
            login="bridge_portal_user",
            groups="base.group_portal",
        )
        cls.env["ir.model.access"].create(
            {
                "name": "ai.bridge.execution user access",
                "model_id": cls.env["ir.model"]._get_id("bridge.test"),
                "perm_create": True,
                "perm_read": True,
                "perm_write": True,
                "perm_unlink": True,
            }
        )

    @classmethod
    def tearDownClass(cls):
        cls.loader.restore_registry()
        super().tearDownClass()

    def test_bridge_creation_user(self):
        self.bridge.write({"usage": "ai_thread_create"})
        self.assertEqual(
            0,
            self.env["ai.bridge.execution"].search_count(
                [("ai_bridge_id", "=", self.bridge.id)]
            ),
        )
        with self.with_user("bridge_user"), mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"result": "success"}
            # Create a test record
            self.env["bridge.test"].create({"name": "Test Record"})
            mock_post.assert_called_once()
        self.assertEqual(
            1,
            self.env["ai.bridge.execution"].search_count(
                [("ai_bridge_id", "=", self.bridge.id)]
            ),
        )

    def test_bridge_creation_portal_user(self):
        self.bridge.write({"usage": "ai_thread_create"})
        self.assertEqual(
            0,
            self.env["ai.bridge.execution"].search_count(
                [("ai_bridge_id", "=", self.bridge.id)]
            ),
        )
        with self.with_user("bridge_portal_user"), mock.patch(
            "requests.post"
        ) as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"result": "success"}
            # Create a test record
            self.env["bridge.test"].create({"name": "Test Record"})
            mock_post.assert_called_once()
        self.assertEqual(
            1,
            self.env["ai.bridge.execution"].search_count(
                [("ai_bridge_id", "=", self.bridge.id)]
            ),
        )

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

    def test_bridge_model_required(self):
        self.assertFalse(self.bridge.model_required)
        self.bridge.usage = "ai_thread_create"
        self.assertTrue(self.bridge.model_required)
        self.bridge.usage = "thread"
        self.assertTrue(self.bridge.model_required)

    def test_bridge_enabled_for_conditions(self):
        self.bridge.write({"usage": "ai_thread_create"})
        record = self.env["bridge.test"].create({"name": "Test Record"})
        with mock.patch.object(
            type(self.bridge), "_enabled_for", return_value=False
        ) as mock_enabled:
            with mock.patch("requests.post") as mock_post:
                mock_post.return_value.status_code = 200
                mock_post.return_value.json.return_value = {"result": "success"}
                initial_count = self.env["ai.bridge.execution"].search_count([])
                self.env["bridge.test"].create({"name": "Test Record 2"})
                final_count = self.env["ai.bridge.execution"].search_count([])
                self.assertEqual(initial_count, final_count)
                mock_enabled.assert_called()
                mock_post.assert_not_called()
        self.bridge.write({"usage": "ai_thread_unlink", "payload_type": "none"})
        with mock.patch.object(
            type(self.bridge), "_enabled_for", return_value=False
        ) as mock_enabled:
            with mock.patch("requests.post") as mock_post:
                mock_post.return_value.status_code = 200
                mock_post.return_value.json.return_value = {"result": "success"}
                initial_count = self.env["ai.bridge.execution"].search_count([])
                record.unlink()
                final_count = self.env["ai.bridge.execution"].search_count([])
                self.assertEqual(initial_count, final_count)
                mock_enabled.assert_called()
                mock_post.assert_not_called()

    def test_prepare_unlink_empty_records(self):
        self.bridge.write({"usage": "ai_thread_unlink", "payload_type": "none"})
        empty_records = self.env["bridge.test"].browse([])
        initial_count = self.env["ai.bridge.execution"].search_count(
            [("ai_bridge_id", "=", self.bridge.id)]
        )
        result = empty_records._prepare_execution_ai_bridges_unlink(empty_records)
        self.assertEqual(len(result), 0)
        self.assertEqual(result._name, "ai.bridge.execution")
        final_count = self.env["ai.bridge.execution"].search_count(
            [("ai_bridge_id", "=", self.bridge.id)]
        )
        self.assertEqual(initial_count, final_count)

    def test_execute_ai_bridges_empty_records(self):
        self.bridge.write({"usage": "ai_thread_create"})
        empty_records = self.env["bridge.test"].browse([])
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"result": "success"}
            empty_records._execute_ai_bridges_for_records(
                empty_records, "ai_thread_create"
            )
            mock_post.assert_not_called()
            execution_count = self.env["ai.bridge.execution"].search_count(
                [("ai_bridge_id", "=", self.bridge.id)]
            )
            self.assertEqual(execution_count, 0)
