# Copyright 2026 Coopdevs
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
import math
from datetime import timedelta

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.http import request as http_request
from odoo.tools import SQL, clean_context

from .ai_tool import (
    ApprovedExecution,
    approved_tool,
    executing_request,
    running_tool,
)

_logger = logging.getLogger(__name__)

DEFAULT_EXPIRATION_HOURS = 24.0
DEFAULT_MAX_PENDING_PER_HOUR = 20
# Security: an LLM writes the arguments; resolving a huge list of ids each
# time someone opens the request would be a denial of service.
MAX_RESOLVED_IDS = 20


class AiToolRequest(models.Model):
    _name = "ai.tool.request"
    _description = "AI Tool Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"
    # Requester and approver only have read access: let them use the chatter.
    # Security: posting or handling activities here never answers a request,
    # only action_approve and action_reject do.
    _mail_post_access = "read"

    # Security: users have no write or create access on this model, and every
    # field is readonly: the frozen call cannot be changed after the request
    # is made. Only the methods below write on it, as superuser, after their
    # own checks.
    name = fields.Char(required=True, readonly=True)
    # Audit: if the tool is removed, the request keeps its name
    tool_id = fields.Many2one("ai.tool", readonly=True, ondelete="set null")
    tool_name = fields.Char(required=True, readonly=True)
    tool_description = fields.Text(related="tool_id.description")
    # Security: what the tool executed when the request was made. If a
    # module update changes it, the request is not executed: its arguments
    # were meant for the old one.
    tool_function = fields.Char(readonly=True)
    tool_model = fields.Char(readonly=True)
    tool_kind = fields.Char(readonly=True)
    # Security: the action runs in the company it was requested in, not in
    # whatever company the approver has active when approving.
    company_id = fields.Many2one("res.company", readonly=True)
    arguments = fields.Text(
        readonly=True, help="Arguments of the tool call, frozen as JSON."
    )
    call_description = fields.Text(
        compute="_compute_call_display",
        help="What the tool will do, in the words of the tool itself.",
    )
    arguments_display = fields.Text(
        string="Arguments (readable)",
        compute="_compute_call_display",
        help="The arguments, with the names of the records they refer to.",
    )
    res_model = fields.Char(string="Model", readonly=True, index=True)
    res_id = fields.Many2oneReference(
        string="Record ID", model_field="res_model", readonly=True, index=True
    )
    record_ref = fields.Reference(
        selection="_selection_record_ref",
        string="Record",
        compute="_compute_record_ref",
    )
    requester_id = fields.Many2one(
        "res.users", required=True, readonly=True, index=True
    )
    approver_id = fields.Many2one(
        "res.users", required=True, readonly=True, index=True, tracking=True
    )
    origin = fields.Char(
        readonly=True, help="Integration that asked for the tool call."
    )
    expiration_date = fields.Datetime(
        readonly=True, help="Empty when the request never expires."
    )
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("done", "Executed"),
            ("rejected", "Rejected"),
            ("expired", "Expired"),
            ("error", "Failed"),
        ],
        required=True,
        default="pending",
        readonly=True,
        tracking=True,
    )
    answer_date = fields.Datetime(readonly=True)
    result = fields.Text(readonly=True)
    error = fields.Text(readonly=True)
    record_ids = fields.One2many(
        "ai.tool.request.record",
        "request_id",
        string="Affected Records",
        readonly=True,
        help="Documents created or modified by the action once approved.",
    )
    can_answer = fields.Boolean(compute="_compute_can_answer")

    @api.depends("arguments", "tool_id", "res_model", "res_id")
    @api.depends_context("uid")
    def _compute_call_display(self):
        """An approval is only worth something if the person understands
        what they approve: "user_id": 7 does not say who 7 is.

        Security: names are read with the rights of the person reading the
        request (never as superuser), so it shows nothing they could not
        see otherwise.
        """
        env = self.env(su=False)
        for request in self:
            try:
                arguments = json.loads(request.arguments or "{}")
            except ValueError:
                arguments = {}
            tool = env["ai.tool"].browse(request.tool_id.id)
            record = None
            if request.res_model in env:
                record = env[request.res_model].browse(request.res_id).exists()
            description = False
            if tool:
                try:
                    description = tool._describe_call(arguments, record=record)
                except Exception as e:
                    # A failing description must not hide the request
                    _logger.debug("Cannot describe AI tool request: %s", e)
            request.call_description = description or False
            request.arguments_display = request._format_arguments(
                arguments, tool, record
            )

    @api.depends("res_model", "res_id")
    def _compute_record_ref(self):
        for request in self:
            if request.res_model in self.env and request.res_id:
                request.record_ref = f"{request.res_model},{request.res_id}"
            else:
                request.record_ref = False

    @api.depends("state", "approver_id")
    @api.depends_context("uid")
    def _compute_can_answer(self):
        for request in self:
            request.can_answer = (
                request.state == "pending" and request.approver_id == self.env.user
            )

    @api.model
    def _selection_record_ref(self):
        # From the registry: no need to read ir.model (and no sudo)
        return [
            (name, self.env[name]._description or name) for name in sorted(self.env)
        ]

    def action_approve(self):
        self.ensure_one()
        self._check_can_answer()
        self._execute()
        return True

    def action_reject(self):
        self.ensure_one()
        self._check_can_answer()
        self._write_answer({"state": "rejected", "answer_date": fields.Datetime.now()})
        self._close_activity()
        self._post_on_record(self.env._("%(user)s rejected the AI action %(name)s."))
        return True

    # Creation

    @api.model
    def _create_from_tool_call(self, tool, arguments, record=None):
        if record is not None and len(record) > 1:
            raise ValueError("AI tool requests accept a single record")
        try:
            # Security: no default= serializer. What is stored must be
            # exactly what will run: never a str() of an unknown object.
            # Sorted keys: the same call always freezes the same way, so that
            # duplicates can be found.
            frozen_arguments = json.dumps(arguments, sort_keys=True)
        except (TypeError, ValueError) as e:
            raise ValueError(
                "The arguments of a tool that requires confirmation must be JSON"
            ) from e
        approver = self._get_approver(record)
        call = {
            "tool_id": tool.id,
            "arguments": frozen_arguments,
            "res_model": record._name if record else False,
            "res_id": record.id if record else False,
            "requester_id": self.env.user.id,
            "approver_id": approver.id,
            "company_id": self.env.company.id,
        }
        # Security: an LLM repeating itself, or flooding the approver, must
        # not bury them in requests: they would end up approving without
        # reading.
        duplicate = self._find_pending_duplicate(call)
        if duplicate:
            return duplicate
        self._check_pending_limit(approver)
        # Security: sudo, because nobody can create requests directly: it is
        # what keeps them from being forged or altered. Only here, after the
        # checks above.
        request = self.sudo().create(
            dict(
                call,
                name=self._get_request_name(tool, record, approver),
                tool_name=tool.name,
                tool_function=tool.function_name,
                tool_model=tool._get_model_name(),
                tool_kind=tool.kind,
                origin=self.env.context.get("ai_tool_origin"),
                expiration_date=self._get_expiration_date(),
            )
        )
        request._schedule_confirmation_activity()
        return request.sudo(self.env.su)

    @api.model
    def _find_pending_duplicate(self, call):
        """A pending request for exactly the same call, if any. No sudo: the
        requester can read their own requests."""
        domain = [("state", "=", "pending")] + [
            (fname, "=", value) for fname, value in call.items()
        ]
        domain += [
            "|",
            ("expiration_date", "=", False),
            ("expiration_date", ">", fields.Datetime.now()),
        ]
        return self.search(domain, limit=1)

    @api.model
    def _check_pending_limit(self, approver):
        """Refuse new requests once the approver has received too many in
        the last hour. 0 means no limit. No sudo: the approver is the
        requester, or no person is behind and this runs as superuser."""
        limit = int(
            self._get_config_param(
                "ai_tool_confirm.max_pending_per_hour", DEFAULT_MAX_PENDING_PER_HOUR
            )
        )
        if limit <= 0:
            return
        count = self.search_count(
            [
                ("approver_id", "=", approver.id),
                ("state", "=", "pending"),
                ("create_date", ">=", fields.Datetime.now() - timedelta(hours=1)),
            ]
        )
        if count >= limit:
            # The message goes back to the LLM: tell it to stop
            raise UserError(
                self.env._(
                    "Too many AI actions are waiting for the confirmation of "
                    "%(user)s (%(count)s in the last hour). Do not request more "
                    "until they have been answered.",
                    user=approver.name,
                    count=count,
                )
            )

    @api.model
    def _get_config_param(self, key, default=None):
        # Security: sudo, as Odoo itself does: only administrators can read
        # ir.config_parameter. It reads this module's settings only.
        return self.env["ir.config_parameter"].sudo().get_param(key, default)

    @api.model
    def _get_request_name(self, tool, record, approver):
        if not record:
            return tool.name
        # Security: the name is shown to the approver (and in their activity):
        # read it with their rights, never as superuser. Without access, the
        # name of the model and the id only.
        record = record.with_user(approver).sudo(False)
        if record._filtered_access("read"):
            return f"{tool.name}: {record.display_name}"
        return f"{tool.name}: {record._description} #{record.id}"

    @api.model
    def _is_valid_approver(self, user):
        # Security: only active internal users answer requests. An archived
        # user would leave requests stuck; an external one must not decide.
        return bool(user) and user.active and user._is_internal()

    @api.model
    def _get_approver(self, record=None):
        """Whoever executes the tool approves it: the user it runs as or,
        when code runs it as OdooBot within a web request, the user of that
        request. Requests with no person behind (scheduled actions, job
        queues, webhooks) go to the responsible user of the record, or else
        to the configured fallback approver."""
        user = self.env.user
        if user._is_superuser():
            # Code may run the tool as OdooBot within a web request (e.g.
            # to post as OdooBot). Then whoever is behind that request is
            # the one executing it, and the one who approves.
            user = self._get_web_user() or user
        if not user._is_superuser():
            # Security: portal and public users cannot make AI tool requests,
            # neither directly nor through code running as OdooBot for them
            # (a website chatbot). Otherwise an external user could get an
            # internal one to execute actions with internal access rights.
            if not self._is_valid_approver(user):
                raise AccessError(
                    self.env._("Only internal users can request AI actions.")
                )
            return user
        # No person behind: a scheduled action, a job queue, a webhook...
        # This already runs as superuser: no sudo needed.
        if record and "user_id" in record._fields:
            field = record._fields["user_id"]
            responsible = (
                field.comodel_name == "res.users" and record.with_env(self.env).user_id
            )
            if self._is_valid_approver(responsible):
                return responsible
        fallback_id = self._get_config_param("ai_tool_confirm.fallback_approver_id")
        fallback = self.env["res.users"].browse(int(fallback_id or 0)).exists()
        if self._is_valid_approver(fallback):
            return fallback
        raise UserError(
            self.env._(
                "Nobody can confirm this AI action: no person executes it, the "
                "record has no responsible user and no valid fallback approver "
                "is configured."
            )
        )

    @api.model
    def _get_web_user(self):
        """The user of the web request being served, if any: the logged in
        user, or the public user for anonymous visitors. None without a web
        request, or for routes without authentication (auth="none": job
        queues, webhooks), which are not people.

        Security: it comes from the session, set by Odoo at login: neither
        the LLM nor the browser can forge it.
        """
        env = http_request and getattr(http_request, "env", None)
        if not env or not env.uid:
            return None
        return self.env["res.users"].browse(env.uid)

    @api.model
    def _get_expiration_date(self):
        """The caller may set the expiration of the request through the
        context; otherwise the instance default applies. 0 means never."""
        hours = self.env.context.get("ai_tool_confirm_expiration_hours")
        if hours is None:
            hours = self._get_config_param(
                "ai_tool_confirm.expiration_hours", DEFAULT_EXPIRATION_HOURS
            )
        hours = float(hours)
        # Security: reject inf, nan and negative values instead of failing
        # later in an unexpected way.
        if not math.isfinite(hours) or hours < 0:
            raise ValueError("The expiration of an AI tool request must be >= 0")
        if not hours:
            return False
        return fields.Datetime.now() + timedelta(hours=hours)

    def _schedule_confirmation_activity(self):
        for request in self:
            request.activity_schedule(
                "ai_tool_confirm.mail_activity_type_ai_tool_confirm",
                date_deadline=request.expiration_date
                and fields.Date.to_date(request.expiration_date),
                user_id=request.approver_id.id,
                summary=self.env._("Confirm AI action: %s", request.name),
            )

    def _get_pending_response(self):
        """What the caller of the tool (an LLM, an MCP client) receives."""
        self.ensure_one()
        return {
            "status": "pending_confirmation",
            "request_id": self.id,
            "message": (
                "The action has not been executed yet. It is waiting for "
                f"{self.approver_id.name} to confirm it in Odoo."
            ),
        }

    # Display

    def _format_arguments(self, arguments, tool, record):
        """One line per argument. Ids are followed by the names of their
        records when a model of the call (the record's, the tool's) has a
        relational field with the same name as the argument."""
        models_to_check = []
        if record is not None:
            models_to_check.append(record)
        if tool:
            tool_model = tool._get_model_name()
            if tool_model in self.env:
                models_to_check.append(self.env[tool_model])
        lines = []
        for name, value in arguments.items():
            line = f"{name}: {json.dumps(value, ensure_ascii=False)}"
            comodel = next(
                (
                    model._fields[name].comodel_name
                    for model in models_to_check
                    if name in model._fields and model._fields[name].relational
                ),
                None,
            )
            names = comodel and self._get_record_names(comodel, value)
            if names:
                line += f" → {names}"
            lines.append(line)
        return "\n".join(lines) or False

    def _get_record_names(self, comodel, value):
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            ids = [value]
        elif isinstance(value, list) and all(
            isinstance(v, int) and not isinstance(v, bool) for v in value
        ):
            ids = value
        else:
            # Odoo commands, names, ... are shown as they are
            return None
        if comodel not in self.env:
            return None
        env = self.env(su=False)
        hidden = len(ids) - MAX_RESOLVED_IDS
        records = env[comodel].browse(ids[:MAX_RESOLVED_IDS])
        existing = records.exists()
        # Security: check the access rules explicitly. Reading a name that is
        # already in the cache (e.g. read as superuser earlier in the same
        # request) does not check them.
        accessible = existing._filtered_access("read")
        names = []
        for record in records:
            if record not in existing:
                names.append(self.env._("%s: not found", record.id))
            elif record not in accessible:
                names.append(self.env._("%s: not accessible", record.id))
            else:
                names.append(record.display_name)
        if hidden > 0:
            names.append(self.env._("… and %s more", hidden))
        return ", ".join(names)

    # Answer

    def _is_interactive_session(self):
        # Security: answers must come from a person using the web client.
        # XML-RPC and JSON-RPC calls (API keys, scripts, AI agents holding the
        # user's credentials) have no authenticated web session, and Odoo does
        # not open web sessions with API keys.
        return bool(http_request) and http_request.session.uid == self.env.uid

    def _check_can_answer(self):
        # Security: an AI tool must never answer a request. Otherwise an LLM
        # with a tool able to call methods could approve its own actions.
        if running_tool.get():
            raise AccessError(self.env._("AI tools cannot answer AI tool requests."))
        if not self._is_interactive_session():
            raise AccessError(
                self.env._("AI tool requests can only be answered from Odoo.")
            )
        # Security: lock the requests before checking their state, so two
        # simultaneous answers cannot both see them pending and run the tool
        # twice (the second one waits for a retry and finds them answered).
        self.env.cr.execute(
            SQL(
                "SELECT id FROM %s WHERE id IN %s FOR UPDATE NOWAIT",
                SQL.identifier(self._table),
                tuple(self.ids),
            )
        )
        self.invalidate_recordset(["state"])
        for request in self:
            if request.state != "pending":
                raise UserError(
                    self.env._("The AI request %s is not pending.", request.name)
                )
            # Security: only the approver answers, not even the superuser on
            # their behalf.
            if request.approver_id != self.env.user:
                raise UserError(
                    self.env._(
                        "Only %(user)s can answer the AI request %(name)s.",
                        user=request.approver_id.name,
                        name=request.name,
                    )
                )
            # Security: checked here too, not only by the cron, which may not
            # have run yet.
            if request.expiration_date and (
                request.expiration_date < fields.Datetime.now()
            ):
                raise UserError(
                    self.env._("The AI request %s has expired.", request.name)
                )

    def _write_answer(self, vals):
        # Security: sudo, because nobody can write on requests directly: it
        # is what keeps them from being altered. Only after _check_can_answer.
        self.sudo().write(vals)

    def _execute(self):
        """Run the tool with the access rights of the approver."""
        self.ensure_one()
        # Security: never as superuser, even if this method is reached from
        # a sudo() environment: the approver's own rights apply. Without the
        # default_* keys of the approver's web context: they would fill
        # fields of the records the tool creates.
        env = self.env(su=False, context=clean_context(self.env.context))
        if self.company_id:
            env = env(
                context=dict(env.context, allowed_company_ids=self.company_id.ids)
            )
        tool = env["ai.tool"].browse(self.tool_id.id)
        record = None
        if self.res_model:
            record = env[self.res_model].browse(self.res_id).exists()
        arguments = json.loads(self.arguments or "{}")
        vals = {"answer_date": fields.Datetime.now()}
        # Security: only this tool, and only during this call, skips the
        # confirmation.
        token = approved_tool.set(tool.id)
        execution = ApprovedExecution(self)
        modified = set()
        request_token = executing_request.set(execution)
        try:
            if not tool:
                raise UserError(self.env._("The AI tool no longer exists."))
            if (
                tool.function_name,
                tool._get_model_name(),
                tool.kind,
            ) != (self.tool_function, self.tool_model, self.tool_kind):
                raise UserError(
                    self.env._("The AI tool has changed since the request was made.")
                )
            if self.company_id and self.company_id not in self.env.user.company_ids:
                raise UserError(
                    self.env._(
                        "You do not have access to the company where this "
                        "action was requested."
                    )
                )
            if record is not None and not record:
                raise UserError(self.env._("The record no longer exists."))
            # Audit: logged inside the savepoint, so that if the action
            # fails its trace is undone with it.
            with self.env.cr.savepoint():
                result = tool._execute_tool(record=record, **arguments)
                modified = self._log_modified_records(execution)
        except Exception as e:
            _logger.info("AI tool request %s failed: %s", self.id, e)
            vals.update({"state": "error", "error": str(e)})
            message = self.env._(
                "%(user)s approved the AI action %(name)s, but it failed."
            )
        else:
            vals.update({"state": "done", "result": json.dumps(result, default=str)})
            message = self.env._(
                "%(user)s approved and executed the AI action %(name)s."
            )
        finally:
            approved_tool.reset(token)
            executing_request.reset(request_token)
        self._write_answer(vals)
        self._close_activity()
        # The context record already says it was modified by this request:
        # one message is enough.
        if vals["state"] == "error" or (self.res_model, self.res_id) not in modified:
            self._post_on_record(message)

    def _close_activity(self):
        # No sudo: the activity is the approver's, and the request accepts
        # messages from those who can read it (_mail_post_access).
        self.activity_feedback(["ai_tool_confirm.mail_activity_type_ai_tool_confirm"])

    def _post_on_record(self, message):
        """Leave a trace on the chatter of the affected record."""
        self.ensure_one()
        if not self.res_model:
            return
        if not self.env[self.res_model].browse(self.res_id).exists():
            return
        # Security: a plain string body is escaped by _message_log, so user
        # and tool names cannot inject HTML.
        body = message % {"user": self.env.user.name, "name": self.tool_name}
        self._log_audit_note(self.res_model, self.res_id, body, self.env.user)

    # Audit trail

    def _get_audit_body(self, text):
        # Security: Markup % escapes the user names; the request link comes
        # from _get_html_link, which escapes its title.
        return Markup(text) % {
            "approver": self.approver_id.name,
            "requester": self.requester_id.name,
            "request": self._get_html_link(),
        }

    def _log_created_records(self, records):
        """Audit: link the records created by this approved request to it,
        and say so in their chatter. Runs inside the savepoint of the
        execution: if the action fails, this is undone with the records."""
        self.ensure_one()
        self._create_audit_lines(
            [
                {"operation": "create", "res_model": rec._name, "res_id": rec.id}
                for rec in records
            ]
        )
        body = self._get_audit_body(
            self.env._(
                "Created by an AI action approved by %(approver)s, "
                "requested by %(requester)s: %(request)s"
            )
        )
        records.with_env(self.env)._message_log_batch(
            dict.fromkeys(records.ids, body),
            author_id=self.approver_id.partner_id.id,
        )

    def _create_audit_lines(self, vals_list):
        # Security: sudo, because nobody can create audit lines directly: it
        # is what keeps the audit trail from being forged. Only from the
        # execution of an approved request.
        self.ensure_one()
        self.env["ai.tool.request.record"].sudo().create(
            [dict(vals, request_id=self.id) for vals in vals_list]
        )

    def _log_audit_note(self, model, res_id, body, author):
        """An internal note on a document, for the audit trail.

        _message_log is Odoo's API for log notes: internal, it notifies
        nobody and subscribes nobody, and it does not depend on the rights of
        the user (it creates the message as superuser itself). The audit
        trail must not depend on whether the approver can post on the
        document.
        """
        record = self.env[model].browse(res_id)
        if hasattr(record, "_message_log"):
            record._message_log(body=body, author_id=author.partner_id.id)

    def _log_modified_records(self, execution):
        """Audit: link the documents modified by this approved request to it,
        and say so in their chatter, in a single message per document. The
        AI proposes, the user disposes.

        Odoo already logs the changes of tracked fields in one message:
        this text becomes its body. Changes it does not log (untracked
        fields, or tracking disabled) are named in it too; if Odoo logs
        nothing, the message is posted here.

        :return: {(model, id)} of the documents really modified
        """
        self.ensure_one()
        modified = set()
        for (model, res_id), initial in execution.initial_values.items():
            if (model, res_id) in execution.created:
                continue
            # Security: sudo, because the action may leave the approver
            # unable to read the record (e.g. assigned to someone else, under
            # a "my records only" rule), and failing here would undo the
            # action. These values are only compared, never shown: the audit
            # only names the fields that changed.
            record = self.env[model].sudo().browse(res_id).exists()
            if not record:
                continue
            changed = [fname for fname, old in initial.items() if record[fname] != old]
            if not changed:
                continue
            modified.add((model, res_id))
            self._create_audit_lines(
                [{"operation": "write", "res_model": model, "res_id": res_id}]
            )
            body = self._get_audit_body(
                self.env._(
                    "Proposed by an AI and approved by %(approver)s, "
                    "requested by %(requester)s: %(request)s"
                )
            )
            # Fields Odoo will log by itself at commit. Not all the tracked
            # ones: tracking may be disabled (tracking_disable, mail_notrack)
            # and then the AI text would be lost with it.
            pending = self.env.cr.precommit.data.get(f"mail.tracking.{model}", {}).get(
                res_id
            )
            natively_logged = set(pending or ()).intersection(changed)
            others = [fname for fname in changed if fname not in natively_logged]
            if others:
                labels = ", ".join(
                    record._fields[fname]._description_string(self.env)
                    for fname in others
                )
                body += Markup("<br/>") + self.env._("Also changed: %s", labels)
            if natively_logged and self._is_public_tracking(
                record, {fname: initial[fname] for fname in natively_logged}
            ):
                # Odoo will send its tracking message to the followers,
                # customers included: say who approved it, in plain words
                # meant for them, without internal details; those go in an
                # internal note, if any.
                record._track_set_log_message(
                    Markup(self.env._("Proposed by an AI and approved by %s"))
                    % self.approver_id.name
                )
                if others:
                    self._log_audit_note(model, res_id, body, self.approver_id)
            elif natively_logged:
                record._track_set_log_message(body)
            else:
                self._log_audit_note(model, res_id, body, self.approver_id)
        return modified

    @api.model
    def _is_public_tracking(self, record, initial_values):
        """Whether Odoo will post the tracking message of these changes with
        a public subtype, so that it reaches external followers too."""
        subtype = record._track_subtype(initial_values)
        if isinstance(subtype, str):
            subtype = self.env.ref(subtype, raise_if_not_found=False)
        return bool(subtype) and not subtype.internal

    # Expiration

    @api.model
    def _cron_expire_requests(self):
        requests = self.search(
            [
                ("state", "=", "pending"),
                ("expiration_date", "!=", False),
                ("expiration_date", "<", fields.Datetime.now()),
            ]
        )
        requests.write({"state": "expired"})
        requests.activity_unlink(["ai_tool_confirm.mail_activity_type_ai_tool_confirm"])
