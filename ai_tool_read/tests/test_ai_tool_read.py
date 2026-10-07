# Copyright 2026 Quartile (https://www.quartile.co)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError, UserError
from odoo.tests.common import TransactionCase, new_test_user

from odoo.addons.ai_tool_read.models.ir_model import MAX_LIMIT


class TestAiToolRead(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        IrModelFields = cls.env["ir.model.fields"]
        # ``ai_no_read`` is configuration data an administrator may already have
        # set in the database, so start from a known state: only res.partner.email
        # is forbidden for the whole test class.
        IrModelFields.search([("ai_no_read", "=", True)]).ai_no_read = False
        cls.email_field = IrModelFields.search(
            [("model", "=", "res.partner"), ("name", "=", "email")], limit=1
        )
        cls.email_field.ai_no_read = True
        cls.partner = cls.env["res.partner"].create(
            {"name": "Tanaka", "email": "tanaka@example.com"}
        )
        cls.user = new_test_user(cls.env, login="ai_reader", groups="base.group_user")
        cls.system_user = new_test_user(
            cls.env, login="ai_admin", groups="base.group_user,base.group_system"
        )

    def _tool(self, name):
        return self.env.ref(f"ai_tool_read.{name}_tool").with_user(self.user)

    def _search_read(self, model="res.partner", user=None, **kwargs):
        return (
            self.env["ir.model"]
            .with_user(user or self.user)
            ._ai_search_read(model, **kwargs)
        )

    def _get_fields(self, model):
        return self.env["ir.model"].with_user(self.user)._ai_get_fields(model)

    def test_agent_workflow(self):
        # The way an agent uses the module, through the ai.tool records: find a
        # model, learn its fields, then read records.
        for name in ("list_models", "get_fields", "search_read"):
            definition = self._tool(name)._get_tool_definition()
            self.assertIn("properties", definition["inputSchema"])
        models = [
            m["model"] for m in self._tool("list_models")._execute_tool()["models"]
        ]
        self.assertIn("res.partner", models)
        self.assertNotIn("ir.cron", models)  # no read access
        self.assertNotIn("mail.compose.message", models)  # wizard, though readable
        res = self._tool("get_fields")._execute_tool(model="res.partner")
        self.assertEqual(res["fields"]["parent_id"]["relation"], "res.partner")
        self.assertNotIn("email", res["fields"])
        self.assertIn("email", res["hidden"])
        res = self._tool("search_read")._execute_tool(
            model="res.partner", domain=[("id", "=", self.partner.id)]
        )
        record = res["records"][0]
        self.assertEqual(record["name"], "Tanaka")
        self.assertNotIn("email", record)  # forbidden
        self.assertNotIn("image_1920", record)  # binary
        self.assertNotIn("contact_address", record)  # computed, not asked for
        self.assertIsInstance(record["create_date"], str)  # JSON-serializable
        self.assertFalse(res["has_more"])

    def test_explicit_fields(self):
        # A field computed on the fly is read when asked for, and a forbidden or
        # binary one is left out, the record still coming with its id.
        domain = [("id", "=", self.partner.id)]
        res = self._search_read(
            domain=domain, fields=["name", "email", "contact_address"]
        )
        self.assertEqual(set(res["records"][0]), {"id", "name", "contact_address"})
        res = self._search_read(domain=domain, fields=["email", "image_1920"])
        self.assertEqual(res["records"], [{"id": self.partner.id}])

    def test_no_readable_field(self):
        # With every field forbidden, records come with their id only: an empty
        # field list must not reach read(), which reads all fields for it.
        partner_fields = self.env["ir.model.fields"].search(
            [("model", "=", "res.partner")]
        )
        partner_fields.ai_no_read = True
        res = self._search_read(domain=[("id", "=", self.partner.id)])
        self.assertEqual(res["records"], [{"id": self.partner.id}])

    def test_relational_read_as_id(self):
        # Core adds the display name of a many2one, built from fields of the
        # related record that may be forbidden there (a partner's name).
        child = self.env["res.partner"].create(
            {"name": "Suzuki", "parent_id": self.partner.id}
        )
        res = self._search_read(
            domain=[("id", "=", child.id)], fields=["parent_id", "child_ids"]
        )
        self.assertEqual(
            res["records"],
            [{"id": child.id, "parent_id": self.partner.id, "child_ids": []}],
        )

    def test_paging(self):
        partners = self.env["res.partner"].create(
            [{"name": f"Page {i}"} for i in range(3)]
        )
        kwargs = {
            "domain": [("id", "in", partners.ids)],
            "fields": ["name"],
            "order": "id",
        }
        res = self._search_read(limit=2, **kwargs)
        self.assertEqual([r["id"] for r in res["records"]], partners[:2].ids)
        self.assertTrue(res["has_more"])
        res = self._search_read(limit=2, offset=2, **kwargs)
        self.assertEqual([r["id"] for r in res["records"]], partners[2:].ids)
        self.assertFalse(res["has_more"])

    def test_limit_capped(self):
        # A missing or out-of-range limit falls back to the cap, which Odoo would
        # otherwise lift for a limit of 0 or less.
        partners = self.env["res.partner"].create(
            [{"name": f"Cap {i}"} for i in range(MAX_LIMIT + 1)]
        )
        for limit in (None, -1, 0, MAX_LIMIT + 1):
            with self.subTest(limit=limit):
                res = self._search_read(
                    domain=[("id", "in", partners.ids)], fields=["id"], limit=limit
                )
                self.assertEqual(len(res["records"]), MAX_LIMIT)
                self.assertTrue(res["has_more"])

    def test_forbidden_value_followed(self):
        # A field exposing the value of a forbidden one is forbidden too: one
        # computed from it, related to it, or delegated through _inherits.
        res = self._get_fields("res.partner")
        for name in ("email_normalized", "email_formatted"):
            with self.subTest(name=name):
                self.assertIn(name, res["hidden"])
                self.assertNotIn(name, res["fields"])
        for model in ("res.users", "mail.followers"):
            with self.subTest(model=model):
                self.assertNotIn("email", self._get_fields(model)["fields"])
        # Followed through several levels.
        self.env["ir.model.fields"].search(
            [("model", "=", "res.partner"), ("name", "=", "name")]
        ).ai_no_read = True
        res = self._get_fields("res.partner")
        for name in ("display_name", "commercial_company_name", "parent_name"):
            with self.subTest(name=name):
                self.assertIn(name, res["hidden"])
        # A field merely pointing to the record is not affected.
        self.assertIn("parent_id", res["fields"])

    def test_flag_on_mixin(self):
        # A flag set on a mixin's field applies to the models inheriting it.
        self.email_field.ai_no_read = False
        self.assertIn("email_normalized", self._get_fields("res.partner")["fields"])
        self.env["ir.model.fields"].search(
            [("model", "=", "mail.thread.blacklist"), ("name", "=", "email_normalized")]
        ).ai_no_read = True
        self.assertIn("email_normalized", self._get_fields("res.partner")["hidden"])

    def test_display_name_hidden(self):
        # A display name computed on the fly may show another record's name
        # with nothing in the field dependencies to tell: a follower shows its
        # partner's name. display_name is never stored, so it is left out
        # everywhere; a stored one would declare its dependencies like any
        # computed field.
        self.assertNotIn("display_name", self._get_fields("mail.followers")["fields"])
        self.assertNotIn("display_name", self._get_fields("res.partner")["fields"])

    def test_unreadable_fields_not_exposed(self):
        # A group-restricted field is not even reported as hidden.
        res = self._get_fields("mail.guest")
        self.assertNotIn("access_token", res["fields"])
        self.assertNotIn("access_token", res["hidden"])
        # A field pointing to a model the user cannot read is left out, so that
        # reading the model does not fail as a whole.
        self.assertNotIn("model_access", self._get_fields("res.groups")["fields"])
        group_user = self.env.ref("base.group_user")
        res = self._search_read("res.groups", domain=[("id", "=", group_user.id)])
        self.assertNotIn("model_access", res["records"][0])
        # A user who may read them gets them.
        res = self._search_read(
            "res.groups",
            user=self.system_user,
            domain=[("id", "=", group_user.id)],
            fields=["model_access"],
        )
        self.assertIn("model_access", res["records"][0])

    def test_refused_field_left_out(self):
        # A computed field can be refused only when it is computed, typically
        # because its compute looks up a model the user cannot read. Simulated,
        # as which real fields do so depends on the installed modules, and a
        # value already in the cache would not be computed at all.
        def compute_refused(partners):
            partners.env["ir.model.access"].check_access("read")

        self.patch(
            type(self.env["res.partner"]), "_compute_contact_address", compute_refused
        )
        self.partner.invalidate_recordset(["contact_address"])
        domain = [("id", "=", self.partner.id)]
        res = self._search_read(domain=domain, fields=["name", "contact_address"])
        self.assertEqual(res["records"], [{"id": self.partner.id, "name": "Tanaka"}])
        self.assertEqual(res["inaccessible_fields"], ["contact_address"])

    def test_refused_record_dropped(self):
        # ir.attachment search finds attachments that its read then refuses (no
        # res_model, not public, created by someone else).
        Attachment = self.env["ir.attachment"]
        private = Attachment.create({"name": "private.txt", "raw": b"x"})
        public = Attachment.create({"name": "public.txt", "raw": b"x", "public": True})
        res = self._search_read(
            "ir.attachment",
            domain=[("id", "in", (private | public).ids)],
            fields=["name"],
        )
        self.assertEqual([r["name"] for r in res["records"]], ["public.txt"])
        self.assertEqual(res["inaccessible_fields"], [])

    def test_unqueryable_model_rejected(self):
        for model in ("no.such.model", "mail.thread", "base.language.install"):
            with self.subTest(model=model):
                with self.assertRaises(UserError) as catcher:
                    self._search_read(model)
                self.assertNotIsInstance(catcher.exception, AccessError)
        with self.assertRaises(AccessError):
            self._search_read("ir.cron")
        # An abstract model is not listed even when an ACL grants read on it.
        self.env["ir.model.access"].create(
            {
                "name": "ai_tool_read_test_access",
                "model_id": self.env["ir.model"]._get("mail.thread").id,
                "group_id": self.env.ref("base.group_user").id,
                "perm_read": True,
            }
        )
        models = [
            m["model"] for m in self._tool("list_models")._execute_tool()["models"]
        ]
        self.assertNotIn("mail.thread", models)

    def test_flag_write_on_base_field(self):
        # Core refuses to alter a base field, but the flag goes through.
        self.email_field.write({"ai_no_read": False})
        res = self._search_read(domain=[("id", "=", self.partner.id)], fields=["email"])
        self.assertEqual(res["records"][0]["email"], "tanaka@example.com")
        # Any other key keeps core's validation, with or without the flag.
        for vals in ({"index": True}, {"ai_no_read": True, "index": True}):
            with self.subTest(vals=vals):
                with self.assertRaises(UserError), self.cr.savepoint():
                    self.email_field.write(vals)
