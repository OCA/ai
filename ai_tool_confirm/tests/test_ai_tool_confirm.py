# Copyright 2026 Coopdevs
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time
from odoo_test_helper import FakeModelLoader

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import new_test_user

from odoo.addons.ai_tool_confirm.models.ai_tool import running_tool
from odoo.addons.base.tests.common import BaseCommon


class AiToolConfirmCase(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        groups = "base.group_user,base.group_partner_manager"
        cls.requester = new_test_user(cls.env, "ai_requester", groups=groups)
        cls.other_user = new_test_user(cls.env, "ai_other", groups=groups)
        cls.fallback = new_test_user(cls.env, "ai_fallback", groups=groups)
        cls.admin = new_test_user(
            cls.env, "ai_admin", groups="base.group_user,base.group_system"
        )
        cls.partner = cls.env["res.partner"].create({"name": "AI Partner"})
        cls.post_message = cls.env.ref("ai_tool.post_message")
        cls.get_date = cls.env.ref("ai_tool.current_date")
        cls.Request = cls.env["ai.tool.request"]

    def _call_post_message(self, user=None, **context):
        env = self.env(user=user) if user else self.env
        return (
            self.post_message.with_env(env)
            .with_context(**context)
            ._execute_tool(message="Hello AI", record=self.partner.with_env(env))
        )

    def _request(self, result, user=None):
        request = self.Request.browse(result["request_id"])
        return request.with_user(user) if user else request

    def _partner_messages(self, text):
        return self.partner.message_ids.filtered(lambda m: text in (m.body or ""))


class TestAiToolConfirm(AiToolConfirmCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Tests run without an HTTP request: act as if answers came from the
        # web client. TestAiToolConfirmSession checks the real behaviour.
        cls.startClassPatcher(
            patch.object(
                type(cls.Request), "_is_interactive_session", return_value=True
            )
        )

    def test_read_only_tool_is_executed(self):
        result = self.get_date.with_user(self.requester)._execute_tool()
        self.assertIn("date", result)
        self.assertFalse(self.Request.search([]))

    def test_tool_call_creates_request(self):
        result = self._call_post_message(self.requester, ai_tool_origin="test")
        self.assertEqual(result["status"], "pending_confirmation")
        self.assertFalse(self._partner_messages("Hello AI"))
        request = self._request(result)
        self.assertEqual(request.state, "pending")
        self.assertEqual(request.tool_id, self.post_message)
        self.assertEqual(request.tool_name, "post_message")
        self.assertEqual(request.record_ref, self.partner)
        self.assertEqual(request.requester_id, self.requester)
        self.assertEqual(request.approver_id, self.requester)
        self.assertEqual(request.origin, "test")
        self.assertIn("Hello AI", request.arguments)
        self.assertEqual(request.activity_ids.user_id, self.requester)

    def test_readable_arguments(self):
        """The approver sees who and what the ids of the arguments are."""
        category = self.env["res.partner.category"].create({"name": "AI Tag"})
        hidden = self.env["res.partner.category"].create({"name": "AI Hidden Tag"})
        self.env["ir.rule"].create(
            {
                "name": "Hide a tag",
                "model_id": self.env.ref("base.model_res_partner_category").id,
                "domain_force": f"[('id', '!=', {hidden.id})]",
            }
        )
        result = self.post_message.with_user(self.requester)._execute_tool(
            message="Hello AI",
            user_id=self.other_user.id,
            category_id=[category.id, hidden.id, 999999],
            record=self.partner.with_user(self.requester),
        )
        request = self._request(result, self.requester)
        display = request.arguments_display
        self.assertIn('message: "Hello AI"', display)
        self.assertIn(
            f"user_id: {self.other_user.id} → {self.other_user.name}", display
        )
        # Names read with the rights of the reader: nothing more is disclosed
        self.assertIn(
            f"AI Tag, {hidden.id}: not accessible, 999999: not found", display
        )
        self.assertNotIn("AI Hidden Tag", display)
        # The tool describes its call in plain words
        self.assertIn("Post a message on AI Partner", request.call_description)
        self.assertIn("Hello AI", request.call_description)

    def test_readable_arguments_limit(self):
        """Resolving names is capped: an LLM must not be able to make the
        request slow to open with a huge list of ids."""
        users = self.requester | self.other_user | self.fallback
        ids = users.ids + list(range(10**6, 10**6 + 22))
        result = self.post_message.with_user(self.requester)._execute_tool(
            message="Hello AI",
            user_id=ids,
            record=self.partner.with_user(self.requester),
        )
        display = self._request(result, self.requester).arguments_display
        self.assertIn("… and 5 more", display)
        self.assertEqual(display.count("not found"), 17)

    def test_failing_description(self):
        """A failing description does not hide the request."""
        AiTool = type(self.env["ai.tool"])
        result = self._call_post_message(self.requester)
        request = self._request(result, self.requester)
        with patch.object(
            AiTool, "_ai_post_message_describe", side_effect=ValueError("Broken")
        ):
            self.assertFalse(request.call_description)
            self.assertIn("Hello AI", request.arguments_display)

    def test_approve(self):
        request = self._request(self._call_post_message(self.requester), self.requester)
        self.assertTrue(request.can_answer)
        request.action_approve()
        self.assertEqual(request.state, "done")
        self.assertTrue(request.answer_date)
        self.assertFalse(request.activity_ids)
        message = self._partner_messages("Hello AI")
        self.assertEqual(len(message), 1)
        self.assertEqual(message.create_uid, self.requester)
        self.assertTrue(self._partner_messages("approved and executed"))

    def test_approve_never_as_superuser(self):
        """Even when approving from a sudo() environment, the tool runs with
        the rights of the approver."""
        request = self._request(self._call_post_message(self.requester), self.requester)
        executed_as_su = []
        AiTool = type(self.env["ai.tool"])
        with patch.object(
            AiTool,
            "_ai_post_message",
            autospec=True,
            side_effect=lambda tool, **kw: executed_as_su.append(tool.env.su) or {},
        ):
            request.sudo().action_approve()
        self.assertEqual(executed_as_su, [False])
        self.assertEqual(request.state, "done")

    def _create_partner_tool(self):
        """A generic tool (no record) that creates a new record."""
        executed = []

        def _ai_create_partner(tool, name=None, fail=False):
            executed.append(tool.env.su)
            partner = tool.env["res.partner"].create({"name": name})
            if fail:
                raise ValueError("Failing after the creation")
            return {"id": partner.id}

        self.startPatcher(
            patch.object(
                type(self.env["ai.tool"]),
                "_ai_create_partner",
                _ai_create_partner,
                create=True,
            )
        )
        tool = self.env["ai.tool"].create(
            {
                "name": "create_partner",
                "description": "Create a contact.",
                "model_id": self.env.ref("ai_tool.model_ai_tool").id,
                "function_name": "_ai_create_partner",
                "kind": "generic",
            }
        )
        return tool, executed

    def test_approve_without_record(self):
        """A tool that creates a record: the request has no record, and the
        new record is created by the approver once approved."""
        tool, executed = self._create_partner_tool()
        result = tool.with_user(self.requester)._execute_tool(name="AI New Contact")
        self.assertEqual(result["status"], "pending_confirmation")
        Partner = self.env["res.partner"]
        self.assertFalse(Partner.search([("name", "=", "AI New Contact")]))
        request = self._request(result, self.requester)
        self.assertFalse(request.res_model)
        self.assertFalse(request.record_ref)
        self.assertEqual(request.name, "create_partner")
        self.assertEqual(request.approver_id, self.requester)
        request.action_approve()
        self.assertEqual(request.state, "done")
        self.assertEqual(executed, [False])
        new_partner = Partner.search([("name", "=", "AI New Contact")])
        self.assertEqual(len(new_partner), 1)
        self.assertEqual(new_partner.create_uid, self.requester)
        self.assertIn(str(new_partner.id), request.result)
        # Audit: the new record says it comes from an approved AI action...
        note = new_partner.message_ids.filtered(
            lambda m: "Created by an AI action" in (m.body or "")
        )
        self.assertEqual(len(note), 1)
        self.assertEqual(note.author_id, self.requester.partner_id)
        self.assertIn(f'data-oe-id="{request.id}"', note.body)
        # ... and the request lists it
        self.assertEqual(request.record_ids.record_ref, new_partner)
        self.assertEqual(request.record_ids.operation, "create")
        # Record rules: only the requester and the approver see the list
        RequestRecord = self.env["ai.tool.request.record"]
        self.assertTrue(RequestRecord.with_user(self.requester).search([]))
        self.assertFalse(RequestRecord.with_user(self.other_user).search([]))

    def test_created_records_undone_on_failure(self):
        tool, executed = self._create_partner_tool()
        result = tool.with_user(self.requester)._execute_tool(
            name="AI Failing Contact", fail=True
        )
        request = self._request(result, self.requester)
        request.action_approve()
        self.assertEqual(request.state, "error")
        self.assertFalse(
            self.env["res.partner"].search([("name", "=", "AI Failing Contact")])
        )
        self.assertFalse(request.record_ids)

    def _flush_tracking(self):
        """Odoo logs tracked changes when the transaction is committed."""
        self.env.flush_all()
        self.env.cr.precommit.run()

    def _ai_messages(self, record):
        return record.message_ids.filtered(
            lambda m: "Proposed by an AI" in (m.body or "")
        )

    def _update_contacts_tool(self):
        """A tool that modifies its record (a tracked and an untracked field)
        and another record (an untracked field only)."""
        other = self.env["res.partner"].create({"name": "AI Other Partner"})

        def _ai_update_contacts(tool, record=None, email=None, fail=False):
            record.write({"email": email})
            record.write({"function": "AI Job"})
            record.write({"function": "AI Job"})  # No real change: same message
            other.with_env(tool.env).write({"function": "AI Job"})
            other.with_env(tool.env).write({"comment": other.comment})  # Unchanged
            if fail:
                raise ValueError("Failing after the changes")
            return {}

        self.startPatcher(
            patch.object(
                type(self.env["ai.tool"]),
                "_ai_update_contacts",
                _ai_update_contacts,
                create=True,
            )
        )
        tool = self.env["ai.tool"].create(
            {
                "name": "update_contacts",
                "model_id": self.env.ref("ai_tool.model_ai_tool").id,
                "function_name": "_ai_update_contacts",
                "kind": "generic_model",
            }
        )
        return tool, other

    def test_approve_modifies_records(self):
        """The AI proposes, the user disposes: each modified document gets a
        single message saying so, with its changes."""
        # Odoo's tracking, disabled by default in these tests
        self.env = self.env(
            context=dict(self.env.context, tracking_disable=False, mail_notrack=False)
        )
        self.partner = self.partner.with_env(self.env)
        self.Request = self.Request.with_env(self.env)
        tool, other = self._update_contacts_tool()
        self._flush_tracking()
        before = self.partner.message_ids | other.message_ids
        result = tool.with_user(self.requester)._execute_tool(
            email="ai@example.com", record=self.partner.with_user(self.requester)
        )
        request = self._request(result, self.requester)
        request.action_approve()
        self._flush_tracking()
        self.assertEqual(request.state, "done", request.error)
        # The record of the request: Odoo's own tracking message, with the AI
        # text as body and the untracked field named in it
        new_messages = self.partner.message_ids - before
        self.assertEqual(len(new_messages), 1)
        message = new_messages
        self.assertIn("Proposed by an AI", message.body)
        self.assertIn("Also changed: Job Position", message.body)
        self.assertIn(f'data-oe-id="{request.id}"', message.body)
        self.assertEqual(message.author_id, self.requester.partner_id)
        self.assertEqual(message.tracking_value_ids.field_id.name, "email")
        # Another record, only untracked fields changed: a note of its own
        new_messages = other.message_ids - before
        self.assertEqual(len(new_messages), 1)
        self.assertIn("Proposed by an AI", new_messages.body)
        self.assertIn("Also changed: Job Position", new_messages.body)
        self.assertNotIn("Notes", new_messages.body)
        # The request lists both
        self.assertEqual(
            sorted(request.record_ids.mapped(lambda r: (r.operation, r.res_id))),
            sorted([("write", self.partner.id), ("write", other.id)]),
        )

    def test_modified_records_tracking_disabled(self):
        """With Odoo's tracking disabled, the AI trace is not lost: a note of
        its own names every changed field."""
        tool, other = self._update_contacts_tool()
        result = tool.with_user(self.requester)._execute_tool(
            email="ai@example.com", record=self.partner.with_user(self.requester)
        )
        request = self._request(result, self.requester)
        request.action_approve()
        self._flush_tracking()
        self.assertEqual(request.state, "done", request.error)
        message = self._ai_messages(self.partner)
        self.assertEqual(len(message), 1)
        self.assertIn("Also changed: Email, Job Position", message.body)
        self.assertFalse(message.tracking_value_ids)
        self.assertFalse(self._partner_messages("approved and executed"))

    def test_modified_records_undone_on_failure(self):
        tool, other = self._update_contacts_tool()
        self._flush_tracking()
        result = tool.with_user(self.requester)._execute_tool(
            email="ai@example.com",
            fail=True,
            record=self.partner.with_user(self.requester),
        )
        request = self._request(result, self.requester)
        request.action_approve()
        self._flush_tracking()
        self.assertEqual(request.state, "error")
        self.assertFalse(self.partner.email)
        self.assertFalse(self._ai_messages(self.partner))
        self.assertFalse(self._ai_messages(other))
        self.assertFalse(request.record_ids)
        self.assertTrue(self._partner_messages("but it failed"))

    def test_created_then_modified(self):
        """A record created and then modified by the same action only gets
        the creation note."""
        tool, executed = self._create_partner_tool()
        Partner = type(self.env["res.partner"])
        original_create = Partner.create

        def create_and_write(records, vals_list):
            new = original_create(records, vals_list)
            new.write({"function": "AI Job"})
            return new

        with patch.object(Partner, "create", create_and_write):
            result = tool.with_user(self.requester)._execute_tool(name="AI Twice")
            request = self._request(result, self.requester)
            request.action_approve()
        self._flush_tracking()
        new_partner = self.env["res.partner"].search([("name", "=", "AI Twice")])
        self.assertEqual(new_partner.function, "AI Job")
        self.assertFalse(self._ai_messages(new_partner))
        self.assertEqual(request.record_ids.operation, "create")

    def test_public_tracking_message(self):
        """When Odoo sends the tracking message to external followers, it
        only says who approved it; internal details go in an internal note."""
        self.env = self.env(
            context=dict(self.env.context, tracking_disable=False, mail_notrack=False)
        )
        self.partner = self.partner.with_env(self.env)
        self.Request = self.Request.with_env(self.env)
        tool, other = self._update_contacts_tool()
        self._flush_tracking()
        before = self.partner.message_ids
        public_subtype = self.env.ref("mail.mt_comment")
        self.assertFalse(public_subtype.internal)
        with patch.object(
            type(self.partner), "_track_subtype", return_value=public_subtype
        ):
            result = tool.with_user(self.requester)._execute_tool(
                email="ai@example.com", record=self.partner.with_user(self.requester)
            )
            request = self._request(result, self.requester)
            request.action_approve()
            self._flush_tracking()
        self.assertEqual(request.state, "done", request.error)
        new_messages = self.partner.message_ids - before
        public = new_messages.filtered(lambda m: m.subtype_id == public_subtype)
        self.assertEqual(len(public), 1)
        self.assertIn(
            f"Proposed by an AI and approved by {self.requester.name}", public.body
        )
        self.assertNotIn("requested by", public.body)
        self.assertNotIn("data-oe-id", public.body)
        self.assertNotIn("Also changed", public.body)
        self.assertTrue(public.tracking_value_ids)
        note = new_messages - public
        self.assertEqual(len(note), 1)
        self.assertTrue(note.subtype_id.internal)
        self.assertIn("Also changed: Job Position", note.body)
        self.assertIn(f'data-oe-id="{request.id}"', note.body)

    def test_approval_is_single_use(self):
        """If the approved tool runs an LLM that calls it again, that call
        needs its own confirmation."""
        tool, executed = self._create_partner_tool()
        inner_results = []
        original = type(self.env["ai.tool"])._ai_create_partner

        def create_twice(tool_model, name=None, fail=False):
            if name == "AI Outer":
                inner_results.append(
                    tool.with_env(tool_model.env)._execute_tool(name="AI Inner")
                )
            return original(tool_model, name=name, fail=fail)

        with patch.object(
            type(self.env["ai.tool"]), "_ai_create_partner", create_twice
        ):
            result = tool.with_user(self.requester)._execute_tool(name="AI Outer")
            self._request(result, self.requester).action_approve()
        Partner = self.env["res.partner"]
        self.assertTrue(Partner.search([("name", "=", "AI Outer")]))
        self.assertFalse(Partner.search([("name", "=", "AI Inner")]))
        self.assertEqual(inner_results[0]["status"], "pending_confirmation")

    def test_tool_changed_since_request(self):
        request = self._request(self._call_post_message(self.requester), self.requester)
        self.post_message.function_name = "_ai_get_date"
        request.action_approve()
        self.assertEqual(request.state, "error")
        self.assertIn("changed", request.error)

    def test_runs_in_requested_company(self):
        company_b = self.env["res.company"].create({"name": "AI Company B"})
        self.requester.company_ids |= company_b
        tool, executed = self._create_partner_tool()
        companies = []
        original = type(self.env["ai.tool"])._ai_create_partner

        def record_company(tool_model, name=None, fail=False):
            companies.append(tool_model.env.companies)
            return original(tool_model, name=name, fail=fail)

        result = (
            tool.with_user(self.requester)
            .with_company(company_b)
            ._execute_tool(name="AI Company Contact")
        )
        request = self._request(result, self.requester)
        self.assertEqual(request.company_id, company_b)
        with patch.object(
            type(self.env["ai.tool"]), "_ai_create_partner", record_company
        ):
            # Approved with another company active: it runs in company B only
            request.with_company(self.env.company).action_approve()
        self.assertEqual(request.state, "done", request.error)
        self.assertEqual(companies, [company_b])

    def test_approver_without_company_access(self):
        company_b = self.env["res.company"].create({"name": "AI Company B"})
        self.requester.company_ids |= company_b
        result = (
            self.post_message.with_user(self.requester)
            .with_company(company_b)
            ._execute_tool(message="Hello AI", record=self.partner)
        )
        request = self._request(result, self.requester)
        self.requester.company_ids -= company_b
        request.action_approve()
        self.assertEqual(request.state, "error")
        self.assertIn("You do not have access to the company", request.error)
        self.assertFalse(self._partner_messages("Hello AI"))

    def test_approver_context_defaults_ignored(self):
        """default_* keys of the approver's context do not fill the records
        the tool creates."""
        tool, executed = self._create_partner_tool()
        result = tool.with_user(self.requester)._execute_tool(name="AI Clean")
        request = self._request(result, self.requester)
        request.with_context(default_comment="Injected").action_approve()
        new_partner = self.env["res.partner"].search([("name", "=", "AI Clean")])
        self.assertTrue(new_partner)
        self.assertFalse(new_partner.comment)

    def test_created_records_outside_request(self):
        """Records created by a tool that needs no confirmation, or by
        anything else, are not marked."""
        tool, executed = self._create_partner_tool()
        tool.confirmation = "never"
        tool.with_user(self.requester)._execute_tool(name="AI Direct Contact")
        new_partner = self.env["res.partner"].search(
            [("name", "=", "AI Direct Contact")]
        )
        self.assertTrue(new_partner)
        self.assertFalse(
            new_partner.message_ids.filtered(
                lambda m: "Created by an AI action" in (m.body or "")
            )
        )
        self.assertFalse(self.env["ai.tool.request.record"].search([]))

    def test_automation_without_record_goes_to_fallback(self):
        """With no person behind nor a record, only the fallback
        approver can confirm, and the record is created with their rights."""
        tool, executed = self._create_partner_tool()
        with self.assertRaises(UserError):
            tool._execute_tool(name="AI Automated Contact")
        self.env["ir.config_parameter"].set_param(
            "ai_tool_confirm.fallback_approver_id", str(self.fallback.id)
        )
        request = self._request(tool._execute_tool(name="AI Automated Contact"))
        self.assertEqual(request.approver_id, self.fallback)
        request.with_user(self.fallback).action_approve()
        self.assertEqual(request.state, "done")
        new_partner = self.env["res.partner"].search(
            [("name", "=", "AI Automated Contact")]
        )
        self.assertEqual(new_partner.create_uid, self.fallback)

    def test_reject(self):
        request = self._request(self._call_post_message(self.requester), self.requester)
        request.action_reject()
        self.assertEqual(request.state, "rejected")
        self.assertFalse(request.activity_ids)
        self.assertFalse(self._partner_messages("Hello AI"))
        self.assertTrue(self._partner_messages("rejected"))

    def test_only_approver_can_answer(self):
        request = self._request(self._call_post_message(self.requester))
        # Other users cannot even see the request
        with self.assertRaises(AccessError):
            request.with_user(self.other_user).action_approve()
        # Not even the superuser answers on behalf of the approver
        with self.assertRaises(UserError):
            request.action_approve()
        self.assertEqual(request.state, "pending")

    def test_ai_tool_cannot_answer(self):
        """An AI tool able to call methods must not approve its own request."""
        request = self._request(self._call_post_message(self.requester), self.requester)
        token = running_tool.set(True)
        try:
            with self.assertRaises(AccessError):
                request.action_approve()
        finally:
            running_tool.reset(token)
        self.assertEqual(request.state, "pending")

    def test_context_does_not_skip_confirmation(self):
        """The Odoo context comes from RPC clients: it must not bypass."""
        result = self._call_post_message(self.requester, ai_tool_confirm_execute=True)
        self.assertEqual(result["status"], "pending_confirmation")
        self.assertFalse(self._partner_messages("Hello AI"))

    def test_cannot_answer_twice(self):
        request = self._request(self._call_post_message(self.requester), self.requester)
        request.action_reject()
        with self.assertRaises(UserError):
            request.action_approve()

    def test_requests_cannot_be_modified(self):
        request = self._request(self._call_post_message(self.requester), self.requester)
        with self.assertRaises(AccessError):
            request.write({"arguments": '{"message": "Something else"}'})
        with self.assertRaises(AccessError):
            request.with_user(self.admin).unlink()

    def test_failed_execution(self):
        request = self._request(self._call_post_message(self.requester), self.requester)
        self.partner.unlink()
        request.action_approve()
        self.assertEqual(request.state, "error")
        self.assertTrue(request.error)

    def test_removed_tool(self):
        tool = self.post_message.copy({"name": "temporary_post_message"})
        result = tool.with_user(self.requester)._execute_tool(
            message="Hello AI", record=self.partner.with_user(self.requester)
        )
        request = self._request(result, self.requester)
        tool.unlink()
        self.assertEqual(request.tool_name, "temporary_post_message")
        request.action_approve()
        self.assertEqual(request.state, "error")

    def test_expiration_from_context(self):
        now = fields.Datetime.now()
        with freeze_time(now):
            result = self._call_post_message(
                self.requester, ai_tool_confirm_expiration_hours=2
            )
        request = self._request(result)
        self.assertEqual(request.expiration_date, now + timedelta(hours=2))
        with freeze_time(now + timedelta(hours=3)):
            with self.assertRaises(UserError):
                request.with_user(self.requester).action_approve()
            self.Request._cron_expire_requests()
        self.assertEqual(request.state, "expired")
        self.assertFalse(request.activity_ids)

    def test_expiration_from_settings(self):
        self.env["ir.config_parameter"].set_param(
            "ai_tool_confirm.expiration_hours", "5"
        )
        now = fields.Datetime.now()
        with freeze_time(now):
            result = self._call_post_message(self.requester)
        request = self._request(result)
        self.assertEqual(request.expiration_date, now + timedelta(hours=5))

    def test_no_expiration(self):
        result = self._call_post_message(
            self.requester, ai_tool_confirm_expiration_hours=0
        )
        request = self._request(result)
        self.assertFalse(request.expiration_date)
        with freeze_time(fields.Datetime.now() + timedelta(days=365)):
            self.Request._cron_expire_requests()
        self.assertEqual(request.state, "pending")

    def test_invalid_expiration(self):
        for hours in (-1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                self._call_post_message(
                    self.requester, ai_tool_confirm_expiration_hours=hours
                )

    def test_invalid_calls(self):
        tool = self.post_message.with_user(self.requester)
        # A record that is not a recordset (e.g. sent by an MCP client)
        with self.assertRaises(ValueError):
            tool._execute_tool(message="Hello AI", record=self.partner.id)
        # Arguments that cannot be frozen as JSON
        with self.assertRaises(ValueError):
            tool._execute_tool(message=object(), record=self.partner)
        self.assertFalse(self.Request.search([]))

    def test_portal_user_cannot_request(self):
        portal = new_test_user(self.env, "ai_portal", groups="base.group_portal")
        with self.assertRaises(AccessError):
            self.post_message.with_user(portal)._execute_tool(
                message="Hello AI", record=self.partner
            )

    def test_automation_goes_to_responsible(self):
        """With no person behind (self.env is the superuser), the
        request goes to the responsible user of the record."""
        self.partner.user_id = self.other_user
        request = self._request(self._call_post_message())
        self.assertEqual(request.requester_id, self.env.user)
        self.assertEqual(request.approver_id, self.other_user)
        request.with_user(self.other_user).action_approve()
        self.assertEqual(request.state, "done")
        self.assertEqual(self._partner_messages("Hello AI").create_uid, self.other_user)
        # The approver, not the requester, closes the activity: no sudo needed
        self.assertFalse(request.activity_ids)

    def test_automation_goes_to_fallback(self):
        self.env["ir.config_parameter"].set_param(
            "ai_tool_confirm.fallback_approver_id", str(self.fallback.id)
        )
        request = self._request(self._call_post_message())
        self.assertEqual(request.approver_id, self.fallback)

    def test_automation_skips_invalid_approvers(self):
        self.partner.user_id = self.other_user
        self.other_user.active = False
        self.env["ir.config_parameter"].set_param(
            "ai_tool_confirm.fallback_approver_id", str(self.fallback.id)
        )
        self.fallback.active = False
        with self.assertRaises(UserError):
            self._call_post_message()

    def test_automation_request_name_with_approver_rights(self):
        """The name of the request is read with the approver's rights: a
        record they cannot read only shows its model and id."""
        self.env["ir.config_parameter"].set_param(
            "ai_tool_confirm.fallback_approver_id", str(self.fallback.id)
        )
        self.env["ir.rule"].create(
            {
                "name": "Hide the partner",
                "model_id": self.env.ref("base.model_res_partner").id,
                "domain_force": f"[('id', '!=', {self.partner.id})]",
            }
        )
        request = self._request(self._call_post_message())
        self.assertEqual(request.approver_id, self.fallback)
        self.assertEqual(request.name, f"post_message: Contact #{self.partner.id}")
        self.assertNotIn("AI Partner", request.activity_ids.summary)

    def test_superuser_in_web_request_of_internal_user(self):
        """Code running the tool as OdooBot within the web request of an
        internal user: that user executes it, and approves it."""
        self.partner.user_id = self.other_user
        with patch.object(
            type(self.Request), "_get_web_user", return_value=self.requester
        ):
            request = self._request(self._call_post_message())
        self.assertEqual(request.approver_id, self.requester)

    def test_superuser_in_web_request_of_external_user(self):
        """A website chatbot running the tool as OdooBot for a visitor or a
        portal user: refused, not sent to an internal user."""
        self.partner.user_id = self.other_user
        portal = new_test_user(self.env, "ai_portal2", groups="base.group_portal")
        for web_user in (self.env.ref("base.public_user"), portal):
            with patch.object(
                type(self.Request), "_get_web_user", return_value=web_user
            ):
                with self.assertRaises(AccessError):
                    self._call_post_message()
        self.assertFalse(self.Request.search([]))

    def test_invalid_expiration_setting(self):
        with self.assertRaises(ValidationError):
            self.env["res.config.settings"].create(
                {"ai_tool_confirm_expiration_hours": -1}
            )

    def test_duplicate_request(self):
        """The same call again, while pending, returns the pending request."""
        first = self._call_post_message(self.requester)
        second = self.post_message.with_user(self.requester)._execute_tool(
            record=self.partner.with_user(self.requester), message="Hello AI"
        )
        self.assertEqual(first["request_id"], second["request_id"])
        self.assertEqual(len(self.Request.search([])), 1)
        self.assertEqual(len(self._request(first).activity_ids), 1)
        # Another call is another request
        other = self.post_message.with_user(self.requester)._execute_tool(
            message="Something else", record=self.partner.with_user(self.requester)
        )
        self.assertNotEqual(other["request_id"], first["request_id"])
        # The order of the arguments does not matter
        tool = self.post_message.with_user(self.requester)
        partner = self.partner.with_user(self.requester)
        third = tool._execute_tool(
            message="Hi", user_id=self.other_user.id, record=partner
        )
        fourth = tool._execute_tool(
            user_id=self.other_user.id, message="Hi", record=partner
        )
        self.assertEqual(third["request_id"], fourth["request_id"])

    def test_duplicate_of_answered_or_expired_request(self):
        now = fields.Datetime.now()
        with freeze_time(now):
            first = self._call_post_message(
                self.requester, ai_tool_confirm_expiration_hours=1
            )
        with freeze_time(now + timedelta(hours=2)):
            # The first one has expired: a new request
            second = self._call_post_message(self.requester)
            self.assertNotEqual(first["request_id"], second["request_id"])
            # The second one has been answered: a new request
            self._request(second, self.requester).action_reject()
            third = self._call_post_message(self.requester)
        self.assertNotIn(
            third["request_id"], (first["request_id"], second["request_id"])
        )

    def test_pending_limit(self):
        self.env["ir.config_parameter"].set_param(
            "ai_tool_confirm.max_pending_per_hour", "2"
        )
        tool = self.post_message.with_user(self.requester)
        partner = self.partner.with_user(self.requester)
        tool._execute_tool(message="One", record=partner)
        tool._execute_tool(message="Two", record=partner)
        with self.assertRaises(UserError):
            tool._execute_tool(message="Three", record=partner)
        # Answered requests and older ones do not count
        self.Request.search([], limit=1).with_user(self.requester).action_reject()
        tool._execute_tool(message="Three", record=partner)
        with freeze_time(fields.Datetime.now() + timedelta(hours=2)):
            tool._execute_tool(message="Four", record=partner)
        # Per approver: another user still gets requests
        self.post_message.with_user(self.other_user)._execute_tool(
            message="Other", record=self.partner.with_user(self.other_user)
        )
        # 0: no limit
        self.env["ir.config_parameter"].set_param(
            "ai_tool_confirm.max_pending_per_hour", "0"
        )
        tool._execute_tool(message="Five", record=partner)

    def test_invalid_limit_setting(self):
        with self.assertRaises(ValidationError):
            self.env["res.config.settings"].create(
                {"ai_tool_confirm_max_pending_per_hour": -1}
            )

    def test_audit_note_without_write_access(self):
        """The audit trail does not depend on whether the approver can post
        on the record: a user who can only read it still leaves the note."""
        reader = new_test_user(self.env, "ai_reader", groups="base.group_user")
        self.assertFalse(self.partner.with_user(reader).has_access("write"))
        self.partner.user_id = reader
        request = self._request(self._call_post_message())
        self.assertEqual(request.approver_id, reader)
        request.with_user(reader).action_reject()
        self.assertEqual(request.state, "rejected")
        self.assertTrue(self._partner_messages("rejected the AI action"))
        self.assertFalse(request.activity_ids)

    def test_automation_without_approver(self):
        with self.assertRaises(UserError):
            self._call_post_message()

    def test_confirmation_override(self):
        self.post_message.confirmation = "never"
        self.assertFalse(self.post_message.requires_confirmation)
        result = self._call_post_message(self.requester)
        self.assertEqual(result, {})
        self.assertTrue(self._partner_messages("Hello AI"))
        self.get_date.confirmation = "always"
        result = self.get_date.with_user(self.requester)._execute_tool()
        self.assertEqual(result["status"], "pending_confirmation")

    def test_admin_only_changes_confirmation(self):
        tool = self.post_message.with_user(self.admin)
        tool.write({"confirmation": "always"})
        self.assertEqual(self.post_message.confirmation, "always")
        for vals in (
            {"function_name": "unlink"},
            {"read_only": True},
            {"kind": "generic"},
        ):
            with self.assertRaises(AccessError):
                tool.write(vals)


class TestAiToolConfirmSession(AiToolConfirmCase):
    def test_answer_requires_web_session(self):
        """Without a web session (XML-RPC, JSON-RPC with an API key, scripts)
        requests cannot be answered."""
        request = self._request(self._call_post_message(self.requester), self.requester)
        with self.assertRaises(AccessError):
            request.action_approve()
        with self.assertRaises(AccessError):
            request.action_reject()
        self.assertEqual(request.state, "pending")


class TestAiToolConfirmFakeDocument(AiToolConfirmCase):
    """Cases that need a document whose write does not read it back
    (res.partner does)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.loader = FakeModelLoader(cls.env, cls.__module__)
        cls.loader.backup_registry()
        from .fake_models import AiToolConfirmFakeDocument

        cls.loader.update_registry((AiToolConfirmFakeDocument,))
        cls.addClassCleanup(cls.loader.restore_registry)
        cls.Request = cls.env["ai.tool.request"]
        cls.startClassPatcher(
            patch.object(
                type(cls.Request), "_is_interactive_session", return_value=True
            )
        )
        cls.env["ir.model.access"].create(
            {
                "name": "Fake document",
                "model_id": cls.env["ir.model"]._get_id(
                    "ai.tool.confirm.fake.document"
                ),
                "group_id": cls.env.ref("base.group_user").id,
                "perm_read": True,
                "perm_write": True,
                "perm_create": True,
                "perm_unlink": True,
            }
        )
        cls.document = cls.env["ai.tool.confirm.fake.document"].create(
            {"name": "AI Document"}
        )

    def test_audit_when_approver_loses_access(self):
        """The action assigns the document to someone else and, under a "my
        documents only" rule, the approver can no longer read it: the action
        and its audit still work."""
        group = self.env["res.groups"].create({"name": "AI Own Documents"})
        self.requester.groups_id |= group
        self.env["ir.rule"].create(
            {
                "name": "Own documents only",
                "model_id": self.env["ir.model"]._get_id(
                    "ai.tool.confirm.fake.document"
                ),
                "groups": [(4, group.id)],
                "domain_force": "[('user_id', 'in', [user.id, False])]",
                "perm_read": True,
                "perm_write": False,
                "perm_create": False,
                "perm_unlink": False,
            }
        )

        def _ai_assign(tool, record=None, user_id=None):
            record.write({"user_id": user_id})
            # As code using SQL does: the audit cannot rely on the cache
            record.env.invalidate_all()
            return {}

        self.startPatcher(
            patch.object(
                type(self.env["ai.tool"]), "_ai_assign", _ai_assign, create=True
            )
        )
        tool = self.env["ai.tool"].create(
            {
                "name": "assign",
                "model_id": self.env.ref("ai_tool.model_ai_tool").id,
                "function_name": "_ai_assign",
                "kind": "generic_model",
            }
        )
        result = tool.with_user(self.requester)._execute_tool(
            user_id=self.other_user.id,
            record=self.document.with_user(self.requester),
        )
        request = self._request(result, self.requester)
        request.action_approve()
        self.assertEqual(request.state, "done", request.error)
        self.assertEqual(self.document.user_id, self.other_user)
        self.assertFalse(self.document.with_user(self.requester).has_access("read"))
        self.assertEqual(request.record_ids.operation, "write")
        self.assertTrue(
            self.document.message_ids.filtered(
                lambda m: "Proposed by an AI" in (m.body or "")
            )
        )
