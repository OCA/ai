# Copyright 2025 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.tests.common import TransactionCase


class TestDocumentPageAiBridge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.bridge_create = cls.env["ai.bridge"].create(
            {
                "name": "Document Page AI Bridge - Create",
                "description": "<p>Test bridge for document page creation</p>",
                "model_id": cls.env.ref("document_page.model_document_page").id,
                "usage": "ai_thread_create",
                "url": "https://api.example.com/ai/document/create",
                "auth_type": "none",
                "payload_type": "record",
                "result_type": "none",
                "result_kind": "immediate",
                "field_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref(
                                "document_page.field_document_page__content"
                            ).id,
                            cls.env.ref(
                                "document_page.field_document_page__display_name"
                            ).id,
                            cls.env.ref(
                                "document_page.field_document_page__draft_name"
                            ).id,
                        ],
                    )
                ],
            }
        )

        cls.bridge_write = cls.env["ai.bridge"].create(
            {
                "name": "Document Page AI Bridge - Update",
                "description": "<p>Test bridge for document page updates</p>",
                "model_id": cls.env.ref("document_page.model_document_page").id,
                "usage": "ai_thread_write",
                "url": "https://api.example.com/ai/document/update",
                "auth_type": "none",
                "payload_type": "record",
                "result_type": "none",
                "result_kind": "immediate",
                "field_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref(
                                "document_page.field_document_page__content"
                            ).id,
                            cls.env.ref(
                                "document_page.field_document_page__display_name"
                            ).id,
                            cls.env.ref(
                                "document_page.field_document_page__draft_name"
                            ).id,
                        ],
                    )
                ],
            }
        )

        cls.bridge_unlink = cls.env["ai.bridge"].create(
            {
                "name": "Document Page AI Bridge - Delete",
                "description": "<p>Test bridge for document page deletion</p>",
                "model_id": cls.env.ref("document_page.model_document_page").id,
                "usage": "ai_thread_unlink",
                "url": "https://api.example.com/ai/document/delete",
                "auth_type": "none",
                "payload_type": "none",
                "result_type": "none",
                "result_kind": "immediate",
            }
        )

    def test_document_page_create_bridge(self):
        other_bridges = self.env["ai.bridge"].search(
            [
                ("model_id", "=", self.env.ref("document_page.model_document_page").id),
                ("usage", "=", "ai_thread_create"),
                ("id", "!=", self.bridge_create.id),
            ]
        )
        other_bridges.write({"active": False})

        self.bridge_create.write({"usage": "ai_thread_create"})
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Document created"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_create.id)]
                ),
            )
            self.env["document.page"].create(
                {
                    "name": "Test Document Page",
                    "content": "<p>This is a test document page for AI bridge</p>",
                }
            )
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_create.id)]
                ),
            )
            mock_post.assert_called_once()

    def test_document_page_write_bridge(self):
        other_bridges = self.env["ai.bridge"].search(
            [
                ("model_id", "=", self.env.ref("document_page.model_document_page").id),
                ("usage", "=", "ai_thread_write"),
                ("id", "!=", self.bridge_write.id),
            ]
        )
        other_bridges.write({"active": False})

        self.bridge_create.active = False
        document_page = self.env["document.page"].create(
            {
                "name": "Test Document Page for Update",
                "content": "<p>Initial content</p>",
            }
        )
        self.bridge_create.active = True
        self.bridge_write.write({"usage": "ai_thread_write"})
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Document updated"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_write.id)]
                ),
            )
            document_page.write(
                {
                    "name": "Updated Document Page",
                    "content": "<p>Updated content for AI bridge test</p>",
                }
            )
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_write.id)]
                ),
            )
            mock_post.assert_called_once()

    def test_document_page_unlink_bridge(self):
        other_bridges = self.env["ai.bridge"].search(
            [
                ("model_id", "=", self.env.ref("document_page.model_document_page").id),
                ("usage", "=", "ai_thread_unlink"),
                ("id", "!=", self.bridge_unlink.id),
            ]
        )
        other_bridges.write({"active": False})

        self.bridge_create.active = False
        document_page = self.env["document.page"].create(
            {
                "name": "Test Document Page for Deletion",
                "content": "<p>Content to be deleted</p>",
            }
        )
        self.bridge_create.active = True
        self.bridge_unlink.write({"usage": "ai_thread_unlink", "payload_type": "none"})
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Document deleted"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_unlink.id)]
                ),
            )
            document_page.unlink()
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_unlink.id)]
                ),
            )
            mock_post.assert_called_once()

    def test_all_bridges_together(self):
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Success"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_create.id)]
                ),
            )
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_write.id)]
                ),
            )
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_unlink.id)]
                ),
            )
            document_page = self.env["document.page"].create(
                {
                    "name": "Complete Test Document",
                    "content": "<p>Initial content for complete test</p>",
                }
            )
            document_page.write({"content": "<p>Updated content for complete test</p>"})
            document_page.unlink()

            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_create.id)]
                ),
            )
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_write.id)]
                ),
            )
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_unlink.id)]
                ),
            )
