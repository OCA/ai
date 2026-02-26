from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestAiThreadContext(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Setup basic company and user for access rights testing
        cls.company = cls.env["res.company"].create({"name": "Test Company Context"})
        cls.user = cls.env["res.users"].create(
            {
                "name": "Test Context User",
                "login": "test_context_user",
                "company_id": cls.company.id,
                "company_ids": [(4, cls.company.id)],
            }
        )

        # Setup related records
        cls.category1 = cls.env["res.partner.category"].create({"name": "Category 1"})
        cls.category2 = cls.env["res.partner.category"].create({"name": "Category 2"})

        # Setup main record
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

    def test_chatter_history_extraction(self):
        """Test extraction of chatter history content."""
        # Add messages to the partner
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

        # Test standard JSON context does not include message_ids
        context_data = thread._get_record_context(self.partner)
        self.assertNotIn("message_ids", context_data)

        # Test chatter history content extraction
        chatter_content = thread._get_chatter_history_content(self.partner)
        self.assertIn("Hello World", chatter_content)
        self.assertIn("First Message", chatter_content)
        self.assertIn("Second Message", chatter_content)
        self.assertIn(self.user.partner_id.name, chatter_content)

        # Test that history is chronological (first message before second message)
        self.assertTrue(
            chatter_content.find("Hello World") < chatter_content.find("Second Message")
        )

        # Test the system prompt integration
        system_prompt = thread._get_system_prompt()
        self.assertEqual(len(system_prompt), 1)
        self.assertEqual(system_prompt[0]["role"], "system")

        system_content = system_prompt[0]["content"]
        self.assertIn("Here is the chatter history of the record:", system_content)
        self.assertIn("Hello World", system_content)
        self.assertIn("Second Message", system_content)
