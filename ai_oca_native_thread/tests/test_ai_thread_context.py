from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestAiThreadContext(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "Test Company Context"})
        cls.user = cls.env["res.users"].create(
            {
                "name": "Test Context User",
                "login": "test_context_user",
                "company_id": cls.company.id,
                "company_ids": [(4, cls.company.id)],
            }
        )
        cls.category1 = cls.env["res.partner.category"].create({"name": "Category 1"})
        cls.category2 = cls.env["res.partner.category"].create({"name": "Category 2"})

        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Complex Partner",
                "email": "complex@test.com",
                "company_id": cls.company.id,
                "category_id": [(6, 0, [cls.category1.id, cls.category2.id])],
                "comment": "This is a comment",
                "image_1920": (
                    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0l"
                    b"EQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
                ),
            }
        )

    def test_get_record_context_success(self):
        """Test that the context extracts valid fields and maps relations properly."""
        thread = (
            self.env["ai.thread"]
            .with_user(self.user)
            .create(
                {
                    "res_model": "res.partner",
                    "res_id": self.partner.id,
                }
            )
        )
        context_data = thread._get_record_context(self.partner)

        self.assertIn("name", context_data)
        self.assertEqual(context_data["name"], "Complex Partner")
        self.assertIn("email", context_data)
        self.assertEqual(context_data["email"], "complex@test.com")
        self.assertIn("comment", context_data)
        self.assertIn("This is a comment", context_data["comment"])

        # Binary/Image fields should be skipped
        self.assertNotIn("image_1920", context_data)

        # Many2one mapping
        self.assertIn("company_id", context_data)
        self.assertEqual(context_data["company_id"], "Test Company Context")

        # Many2many mapping
        self.assertIn("category_id", context_data)
        self.assertIsInstance(context_data["category_id"], list)
        self.assertIn("Category 1", context_data["category_id"])
        self.assertIn("Category 2", context_data["category_id"])

    def test_get_record_context_access_error(self):
        """Test that context extraction fails gracefully on ACL restriction."""
        thread = (
            self.env["ai.thread"]
            .with_user(self.user)
            .create(
                {
                    "res_model": "res.partner",
                    "res_id": self.partner.id,
                }
            )
        )

        with patch.object(
            type(self.partner), "check_access", side_effect=AccessError("No access")
        ):
            context_data = thread._get_record_context(self.partner)
            self.assertEqual(context_data, {})

    def test_get_record_context_missing_record(self):
        """Test when the record is missing or deleted."""
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": 99999,
            }
        )
        missing_partner = self.env["res.partner"].browse(99999)
        context_data = thread._get_record_context(missing_partner)
        self.assertEqual(context_data, {})

    def test_get_record_context_excludes_message_ids(self):
        self.partner.message_post(body="Hello World", author_id=self.user.partner_id.id)
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
            }
        )
        context_data = thread._get_record_context(self.partner)
        self.assertNotIn("message_ids", context_data)

    def test_get_chatter_history_content_extracts_messages_chronologically(self):
        self.partner.message_post(
            body="<p>Hello World</p>",
            subject="First Message",
            author_id=self.user.partner_id.id,
        )
        self.partner.message_post(
            body="Second Message", author_id=self.user.partner_id.id
        )
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
            }
        )
        chatter_content = thread._get_chatter_history_content(self.partner)

        self.assertIn("Hello World", chatter_content)
        self.assertIn("First Message", chatter_content)
        self.assertIn("Second Message", chatter_content)
        self.assertIn(self.user.partner_id.name, chatter_content)
        self.assertTrue(
            chatter_content.find("Hello World") < chatter_content.find("Second Message")
        )

    def test_get_system_prompt_includes_chatter_history(self):
        self.partner.message_post(body="Hello World", author_id=self.user.partner_id.id)
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
            }
        )
        system_prompt = thread._get_system_prompt()
        self.assertEqual(len(system_prompt), 1)
        self.assertEqual(system_prompt[0]["role"], "system")

        system_content = system_prompt[0]["content"]
        self.assertIn("Here is the chatter history of the record:", system_content)
        self.assertIn("Hello World", system_content)

    def test_get_chatter_history_content_allows_subject_without_body(self):
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
            }
        )
        self.partner.message_ids.unlink()
        self.partner.message_post(body="", subject="Only Subject")

        chatter_content = thread._get_chatter_history_content(self.partner)
        self.assertIn("Subject: Only Subject", chatter_content)
        self.assertNotIn("System:\n\n", chatter_content)

    def test_get_chatter_history_content_returns_empty_when_no_valid_text(self):
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
            }
        )
        self.partner.message_ids.unlink()
        msg_id = self.partner.message_post(body="", subject="").id
        self.env["mail.message"].browse(msg_id).write({"body": False, "subject": False})
        self.assertEqual(thread._get_chatter_history_content(self.partner), "")

    def test_get_system_prompt_excludes_context_when_data_is_empty(self):
        thread = (
            self.env["ai.thread"]
            .with_user(self.user)
            .create(
                {
                    "res_model": "res.partner",
                    "res_id": self.partner.id,
                }
            )
        )
        with patch.object(type(thread), "_get_record_context", return_value={}):
            prompt = thread._get_system_prompt()
            self.assertNotIn(
                "Here is the data associated with this record in", prompt[0]["content"]
            )

    def test_get_system_prompt_excludes_chatter_when_model_has_no_message_ids(self):
        country = self.env["res.country"].search([], limit=1)
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.country",
                "res_id": country.id,
            }
        )
        prompt = thread._get_system_prompt()
        self.assertNotIn("Here is the chatter history", prompt[0]["content"])

    def test_get_system_prompt_excludes_chatter_when_messages_are_empty(self):
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
            }
        )
        self.partner.message_ids.unlink()
        prompt = thread._get_system_prompt()
        self.assertNotIn("Here is the chatter history", prompt[0]["content"])

    def test_get_record_context_invalid_x2many(self):
        """Test context extraction when read() returns non-list for x2many."""
        thread = self.env["ai.thread"].create(
            {
                "res_model": "res.partner",
                "res_id": self.partner.id,
            }
        )
        with patch.object(
            type(self.partner), "read", return_value=[{"category_id": "not a list"}]
        ):
            context = thread._get_record_context(self.partner)
            self.assertNotIn("category_id", context)

    def test_get_chatter_history_content_none_record(self):
        res = self.env["ai.thread"]._get_chatter_history_content(None)
        self.assertEqual(res, "")
