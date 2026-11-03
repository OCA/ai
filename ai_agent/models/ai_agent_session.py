# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
from contextlib import contextmanager
from datetime import timedelta

import markdown
from markupsafe import Markup

from odoo import api, fields, models, modules
from odoo.service.model import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY
from odoo.tools import SQL, config
from odoo.tools.mail import html2plaintext, html_sanitize, plaintext2html

_logger = logging.getLogger(__name__)

# Seconds after which a running session lost its cron job, without time limit
DEFAULT_STALE_SECONDS = 900
MAX_STATE_WRITE_TRIES = 5
# Class of the progress notes still in progress (thinking, running a tool)
PENDING_NOTE_CLASS = "o_ai_agent_pending"
# Tables, fenced code, lists right after a paragraph and single line breaks
MARKDOWN_EXTENSIONS = ["extra", "sane_lists", "nl2br"]
PROVISIONAL_TITLE_LENGTH = 40
TITLE_LENGTH = 60
TITLE_PROMPT = (
    "Summarize the topic of this conversation as a title of at most 6 words, "
    "in the language of the user. Answer only with the title, without quotes "
    "or final punctuation."
)


class AiAgentSession(models.Model):
    _name = "ai.agent.session"
    _description = "AI Agent Session"
    _order = "id desc"

    name = fields.Char(required=True, default="Session")
    active = fields.Boolean(default=True)
    agent_id = fields.Many2one(
        "ai.agent",
        required=True,
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        "res.users",
        required=True,
        ondelete="cascade",
    )
    res_model = fields.Char(
        string="Conversation Model",
        help="Model of the record where the conversation actually lives: "
        "either a discuss.channel (direct message) or any other "
        "mail.thread record the agent was mentioned on.",
    )
    res_id = fields.Integer(string="Conversation Record ID")
    channel_id = fields.Many2one(
        "discuss.channel",
        string="Conversation",
        index="btree_not_null",
        ondelete="cascade",
        readonly=True,
        help="The AI agent conversation of Discuss of this session, if any.",
    )
    res_name = fields.Char(
        string="Document",
        readonly=True,
        help="Name of the document the conversation is about, if any.",
    )
    first_message = fields.Text(readonly=True)
    last_activity = fields.Datetime(
        readonly=True,
        index=True,
        help="Last message of the user in the conversation.",
    )
    state = fields.Selection(
        [
            ("idle", "Idle"),
            ("queued", "Queued"),
            ("running", "Running"),
            ("error", "Error"),
        ],
        default="idle",
        required=True,
        readonly=True,
    )
    claimed_at = fields.Datetime(
        readonly=True,
        help="When a cron job took the session to run an iteration. A session "
        "running for longer than the time limit of the cron jobs lost its job "
        "and is marked as failed by the worker cron.",
    )
    error_message = fields.Text(readonly=True)
    pending_message_id = fields.Many2one(
        "mail.message",
        readonly=True,
        ondelete="set null",
        help="Last message of the user waiting for an answer of the agent.",
    )
    turn_ids = fields.One2many("ai.agent.turn", "session_id", readonly=True)
    processed_message_id = fields.Many2one(
        "mail.message",
        readonly=True,
        ondelete="set null",
        help="Last message of the user already answered by the agent.",
    )

    @api.model
    def _get_or_create_session(self, agent, user, res_model, res_id, message=None):
        domain = [
            ("agent_id", "=", agent.id),
            ("user_id", "=", user.id),
            ("active", "=", True),
            ("res_model", "=", res_model),
            ("res_id", "=", res_id),
        ]
        session = self.search(domain, limit=1, order="id desc")
        if session:
            return session
        content = html2plaintext(message.body or "").strip() if message else ""
        values = {
            "name": self._ai_provisional_title(content)
            or f"{agent.name} - {user.name}",
            "agent_id": agent.id,
            "user_id": user.id,
            "res_model": res_model,
            "res_id": res_id,
            "first_message": content or False,
        }
        # sudo: the conversation record, only to link it and read its name
        thread = self.env[res_model].sudo().browse(res_id).exists()
        if thread._name == "discuss.channel":
            if thread.channel_type == "ai_agent":
                values["channel_id"] = thread.id
                document = thread.with_user(user)._ai_get_context_document()
                values["res_name"] = (
                    document.display_name
                    if document
                    else (thread.ai_context or {}).get("action_name") or False
                )
        elif thread:
            values["res_name"] = thread.display_name
        session = self.create(values)
        session._ai_notify_sessions_changed()
        return session

    @api.model
    def _ai_provisional_title(self, content):
        content = " ".join((content or "").split())
        if len(content) > PROVISIONAL_TITLE_LENGTH:
            return content[: PROVISIONAL_TITLE_LENGTH - 1].rstrip() + "…"
        return content

    def _ai_sidebar_info(self):
        """Sessions as plain data for the Discuss sidebar and history."""
        result = []
        for session in self:
            if session.channel_id:
                channel = session.channel_id
                document_model = channel.ai_res_model
                document_id = channel.ai_res_id
            else:
                document_model = session.res_model
                document_id = session.res_id
            result.append(
                {
                    "id": session.id,
                    "name": session.name,
                    "channel_id": session.channel_id.id or False,
                    "res_model": document_model or False,
                    "res_id": document_id or False,
                    "res_name": session.res_name or False,
                    "last_activity": fields.Datetime.to_string(
                        session.last_activity or session.create_date
                    ),
                }
            )
        return result

    def _build_history_from_thread(self, thread, until_message=None):
        """The conversation as AI messages.

        With ``until_message``, the messages of the user written after it are
        left out: they are for the next turn.
        """
        self.ensure_one()
        agent_partner = self.agent_id.user_id.partner_id
        history = []
        # Only comments: the notes posted by the agent while working (tools,
        # reasoning, errors) are notifications and never reach the AI.
        messages = thread.message_ids.filtered(
            lambda m: m.message_type == "comment"
            and m.body
            and (
                not until_message
                or m.id <= until_message.id
                or m.author_id == agent_partner
            )
        ).sorted(key=lambda m: m.id)
        for message in messages:
            content = html2plaintext(message.body or "").strip()
            if not content:
                continue
            role = "assistant" if message.author_id == agent_partner else "user"
            history.append({"role": role, "content": content})
        return history

    def _get_tool_record(self, thread):
        self.ensure_one()
        # A discuss.channel is where the conversation lives, not a business
        # record: tools get its context document, if any, instead.
        if thread._name == "discuss.channel":
            if thread.channel_type == "ai_agent":
                return thread._ai_get_context_document()
            return None
        return thread

    # ------------------------------------------------------------
    # Queue
    # ------------------------------------------------------------

    def _enqueue_turn(self, message):
        """Ask the worker to answer ``message``, without calling the AI.

        ``pending_message_id`` is always written, even while running: a
        concurrent end of turn of the worker then conflicts on this row and
        one of both transactions is retried, so a message arriving right when
        the turn finishes is never left unanswered.
        """
        self.ensure_one()
        session = self.sudo()
        values = {
            "pending_message_id": message.id,
            "last_activity": message.date or fields.Datetime.now(),
        }
        if session.state != "running":
            values.update(state="queued", error_message=False)
        session.write(values)
        self.env.ref("ai_agent.ir_cron_ai_agent_session_worker").sudo()._trigger()

    @api.model
    def _cron_process_queue(self):
        """Run a single iteration of a queued session, then wake up again.

        One iteration (an AI call and the tools it calls) per cron job: the
        time limit of the cron jobs applies to each iteration, never to a
        whole answer.
        """
        self._recover_stale_sessions()
        session = self._claim_next_session()
        if session:
            session._process_iteration()
        if self.sudo().search_count([("state", "=", "queued")], limit=1):
            self.env.ref("ai_agent.ir_cron_ai_agent_session_worker")._trigger()

    @api.model
    def _claim_next_session(self):
        """Take a queued session for this worker, or an empty recordset.

        SKIP LOCKED plus the committed transition to ``running`` guarantee a
        session is only ever processed by a single worker.
        """
        for _try in range(MAX_STATE_WRITE_TRIES):
            try:
                self.flush_model(["state", "active", "write_date"])
                self.env.cr.execute(
                    SQL(
                        "SELECT id FROM ai_agent_session "
                        "WHERE state = 'queued' AND active "
                        # Oldest in the queue first: a session back in the
                        # queue for its next iteration lets the others run
                        "ORDER BY write_date, id LIMIT 1 FOR UPDATE SKIP LOCKED"
                    )
                )
                row = self.env.cr.fetchone()
                if not row:
                    return self.browse()
                session = self.sudo().browse(row[0])
                session.write(
                    {
                        "state": "running",
                        "claimed_at": fields.Datetime.now(),
                        "error_message": False,
                    }
                )
                self._commit()
                return session
            except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
                self.env.cr.rollback()
        return self.browse()

    def _process_iteration(self):
        """Run the next iteration of the turn of the session.

        The iteration is a single transaction, committed at its end: what the
        tools did, the notes and the answer or the state to go on with. The
        next iteration, or the next turn for newer messages of the user, is
        left to another cron job.
        """
        self.ensure_one()
        turn = self._ai_start_turn()
        first_turn = not self.processed_message_id
        try:
            with self.env.cr.savepoint():
                answer = self._run_turn(turn)
        except Exception as e:
            _logger.exception("AI agent session %s failed", self.id)
            self.env.invalidate_all()
            self._fail(str(e) or type(e).__name__)
            return
        self._commit()
        if answer is None:
            self._ai_schedule_next_iteration()
            return
        if not self._ai_post_answer(answer):
            return
        if first_turn:
            self._ai_update_title()
        self._finish_turn(turn.message_id)

    def _ai_post_answer(self, answer):
        """Post the final answer in the conversation. Return whether it was.

        In a transaction of its own, after the iteration: the progress notes
        written meanwhile in their own cursor update the same conversation
        (its members, its last activity), which a transaction older than
        them could not write without a serialization failure.
        """
        for _try in range(MAX_STATE_WRITE_TRIES):
            try:
                self._get_thread().with_user(self.agent_id.user_id).message_post(
                    body=self._ai_markdown_to_html(answer),
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment",
                )
                self._commit()
                return True
            except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
                self.env.cr.rollback()
        self._fail(self.env._("Could not post the answer of the agent"))
        return False

    def _ai_start_turn(self):
        """The turn in progress of the session: going on, or a new one."""
        self.ensure_one()
        turn = self.sudo().turn_ids[:1]
        if not turn:
            turn = (
                self.env["ai.agent.turn"]
                .sudo()
                .create(
                    {"session_id": self.id, "message_id": self.pending_message_id.id}
                )
            )
        return turn

    def _ai_schedule_next_iteration(self):
        """Run the next iteration of the turn in another worker run.

        Puts the session back in the queue and wakes up the cron worker.
        Override it to run the iterations elsewhere, e.g. as queued jobs.
        """
        self._ai_requeue()

    def _ai_requeue(self):
        """Put the session back in the queue and wake up the cron worker."""
        for _try in range(MAX_STATE_WRITE_TRIES):
            try:
                self.invalidate_recordset()
                self.write({"state": "queued", "claimed_at": False})
                self._commit()
                self.env.ref("ai_agent.ir_cron_ai_agent_session_worker")._trigger()
                return
            except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
                self.env.cr.rollback()
        self._fail(self.env._("Could not update the state of the session"))

    def _finish_turn(self, pending):
        """Mark ``pending`` as answered.

        Newer messages of the user written meanwhile are answered by a new
        turn, in another cron job.
        """
        for _try in range(MAX_STATE_WRITE_TRIES):
            try:
                self.invalidate_recordset()
                again = self.pending_message_id.id > pending.id
                self.write(
                    {
                        "processed_message_id": pending.id,
                        "state": "queued" if again else "idle",
                        "claimed_at": False,
                    }
                )
                self.sudo().turn_ids.unlink()
                self._commit()
                if again:
                    self.env.ref("ai_agent.ir_cron_ai_agent_session_worker")._trigger()
                return
            except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
                self.env.cr.rollback()
        self._fail(self.env._("Could not update the state of the session"))

    def _fail(self, error):
        """Leave the session in error and tell it in the conversation."""
        for _try in range(MAX_STATE_WRITE_TRIES):
            try:
                self.invalidate_recordset()
                self.write(
                    {"state": "error", "error_message": error, "claimed_at": False}
                )
                self.sudo().turn_ids.unlink()
                thread = self._get_thread()
                if thread:
                    self._ai_close_pending_notes(thread)
                    self._post_note(thread, self.env._("⚠️ The agent failed: %s", error))
                self._commit()
                return
            except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
                self.env.cr.rollback()

    @api.model
    def _cron_time_limit(self):
        """Seconds a cron job may run before Odoo kills it, or None."""
        limit = config["limit_time_real_cron"]
        if limit is not None and limit < 0:
            # -1: same limit as the HTTP workers
            limit = config["limit_time_real"]
        return limit if limit and limit > 0 else None

    def _stale_seconds(self):
        param = (
            self.env["ir.config_parameter"].sudo().get_param("ai_agent.stale_seconds")
        )
        if param:
            return int(param)
        limit = self._cron_time_limit()
        # An iteration is a single cron job, killed at the time limit: a
        # session running for longer lost its job, no need to wait more
        return limit + 60 if limit else DEFAULT_STALE_SECONDS

    @api.model
    def _recover_stale_sessions(self):
        """Fail the sessions whose cron job died (killed, restarted...).

        ``claimed_at`` is set when a cron job takes the session for one
        iteration: a session still running long after the time limit of the
        cron jobs lost its job, usually killed by an iteration longer than
        that limit. It is never run again by itself, the error is shown.
        """
        limit = fields.Datetime.now() - timedelta(seconds=self._stale_seconds())
        stale = self.sudo().search(
            [("state", "=", "running"), ("claimed_at", "<", limit)]
        )
        time_limit = self._cron_time_limit()
        for session in stale:
            if time_limit:
                error = self.env._(
                    "The answer was interrupted: a step of the agent took longer "
                    "than the time limit (%s seconds).",
                    time_limit,
                )
            else:
                error = self.env._(
                    "The previous answer timed out without any activity."
                )
            session._fail(error)

    def _commit(self):
        """Commit the progress so far, except while running tests.

        Only used by the cron worker, as the workers of ``queue_job`` do: the
        claim of a session must be committed before the (long) AI call so the
        user never waits for its row, and the answer before the state of the
        session, which the user may be writing at the same time.
        """
        if not modules.module.current_test:
            self.env.cr.commit()  # pylint: disable=invalid-commit

    # ------------------------------------------------------------
    # Turn
    # ------------------------------------------------------------

    def _get_thread(self):
        self.ensure_one()
        if not self.res_model or self.res_model not in self.env:
            return None
        thread = self.env[self.res_model].sudo().browse(self.res_id).exists()
        return thread or None

    def _run_turn(self, turn):
        """Answer the conversation as the human user of the session.

        Tools and record run with the rights, language and company of the
        user, exactly as if the user were running them. Only the connection
        is read as superuser, as its settings are restricted to admins.

        Runs a single iteration: the next one is left to another worker run
        through ``turn`` (see ``_ai_next_iteration``). Return the final answer
        of the AI, to be posted by ``_ai_post_answer``, or ``None`` when the
        turn goes on.
        """
        self.ensure_one()
        user = self.user_id
        session = self.with_user(user).with_context(lang=user.lang, tz=user.tz)
        thread = session.env[self.res_model].browse(self.res_id)
        agent = session.agent_id
        messages = []
        system_prompt = agent._ai_get_system_prompt()
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        record = session._get_tool_record(thread)
        if thread._name == "discuss.channel" and thread.channel_type == "ai_agent":
            context_prompt = thread._ai_context_description()
            if context_prompt:
                messages.append({"role": "system", "content": context_prompt})
        messages += session._build_history_from_thread(
            thread, until_message=turn.message_id
        )
        base_length = len(messages)
        messages += turn.messages or []

        # Progress notes of this iteration still to be completed
        progress = {"tools": []}

        def next_iteration(state):
            turn.sudo().write(
                {
                    "messages": state["messages"][base_length:],
                    "iteration": state["iteration"],
                }
            )

        # Preloaded skills are already in the system prompt: only the other
        # skills are left to be loaded on demand as tools.
        executable_tools = agent.tool_ids - agent.skill_ids.tool_id
        result = agent.connection_id.sudo()._run(
            messages=messages,
            tools=executable_tools or None,
            record=record,
            on_step=lambda step: session._on_step(thread, step, progress),
            tool_activity=True,
            next_iteration=next_iteration,
            iteration=turn.iteration or 1,
        )
        if result is None:
            return None
        return result[0]

    # ------------------------------------------------------------
    # Title
    # ------------------------------------------------------------

    def _ai_update_title(self):
        """Rename the session (and its conversation) after the first turn.

        Best effort: any failure keeps the provisional title and is only
        logged, the conversation itself is never affected.
        """
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                title = self._ai_generate_title()
                if title:
                    self.name = title
                    if self.channel_id:
                        self.channel_id.name = title
                self._ai_notify_sessions_changed()
            self._commit()
        except Exception:
            _logger.exception("Could not generate the title of session %s", self.id)
            self.env.invalidate_all()

    def _ai_generate_title(self):
        self.ensure_one()
        user = self.user_id
        session = self.with_user(user).with_context(lang=user.lang, tz=user.tz)
        thread = session.env[self.res_model].browse(self.res_id)
        history = session._build_history_from_thread(thread)
        if not history:
            return False
        messages = [{"role": "system", "content": TITLE_PROMPT}]
        messages += history[:2]
        messages.append({"role": "user", "content": TITLE_PROMPT})
        response = session.agent_id.connection_id.sudo()._run(messages=messages)[0]
        return self._ai_clean_title(response)

    @api.model
    def _ai_clean_title(self, title):
        title = " ".join(html2plaintext(title or "").split())
        title = title.strip("\"'«»“”*#. ")
        if len(title) > TITLE_LENGTH:
            title = title[: TITLE_LENGTH - 1].rstrip() + "…"
        return title

    def _ai_notify_sessions_changed(self):
        """Tell the Discuss sidebar of the user to refresh its sessions."""
        for session in self:
            session.user_id.partner_id._bus_send(
                "ai_agent/sessions_changed", {"agent_id": session.agent_id.id}
            )

    @api.model
    def _ai_markdown_to_html(self, text):
        """Render the Markdown answers of the AI as the HTML of the chat."""
        html = markdown.markdown(text or "", extensions=MARKDOWN_EXTENSIONS)
        return Markup(html_sanitize(html))

    def _on_step(self, thread, step, progress=None):
        """Show the progress of the iteration in the conversation, live.

        "Thinking..." while the AI answers, becoming its collapsible
        reasoning (or removed without one), and a note per tool while it
        runs, ticked when done. The notes are written apart from the
        iteration transaction (see ``_ai_progress_env``): they show up at
        once while the work of the iteration stays uncommitted.
        """
        if progress is None:
            progress = {"tools": []}
        if step["type"] == "llm_call":
            progress["thinking"] = self._ai_note(
                thread, self._ai_pending_body(self.env._("Thinking..."))
            )
        elif step["type"] == "iteration":
            note = progress.pop("thinking", None)
            if step.get("reasoning"):
                body = Markup("<details><summary>%s</summary>%s</details>") % (
                    self.env._("Reasoning"),
                    plaintext2html(step["reasoning"]),
                )
                if note:
                    self._ai_edit_note(thread, note, body)
                else:
                    self._ai_note(thread, body)
            elif note:
                self._ai_drop_note(thread, note)
        elif step["type"] == "tool_call":
            text = step.get("activity") or self.env._("Running %s...", step["tool"])
            note = self._ai_note(thread, self._ai_pending_body(f"⏳ {text}"))
            progress["tools"].append((note, text))
        elif step["type"] == "tool_result":
            note, text = progress["tools"].pop(0) if progress["tools"] else (None, None)
            if step.get("error"):
                body = self.env._(
                    "❌ %(tool)s failed: %(error)s",
                    tool=step["tool"],
                    error=step["error"],
                )
            else:
                body = f"✓ {text or step['tool']}"
            if note:
                self._ai_edit_note(thread, note, body)
            else:
                self._ai_note(thread, body)

    @api.model
    def _ai_pending_body(self, text):
        return Markup('<span class="%s">%s</span>') % (PENDING_NOTE_CLASS, text)

    @contextmanager
    def _ai_progress_env(self):
        """Environment to write the progress notes, committed at once.

        Its own cursor, apart from the iteration transaction, which never
        waits for it: a lock held by the iteration makes the note give up
        instead. In tests, the current environment (nothing is committed).
        """
        if modules.module.current_test:
            yield self.env
            return
        with self.env.registry.cursor() as cr:
            cr.execute("SET LOCAL lock_timeout = '5s'")
            yield self.env(cr=cr)

    def _ai_note(self, thread, body):
        """Post a progress note at once. Return its id, None if it failed."""
        try:
            with self._ai_progress_env() as env:
                message = self.with_env(env)._post_note(
                    env[thread._name].browse(thread.id), body
                )
                return message.id
        except Exception:
            _logger.warning(
                "Could not post a note of AI agent session %s", self.id, exc_info=True
            )
            return None

    def _ai_edit_note(self, thread, message_id, body):
        """Replace the body of a progress note, at once."""
        try:
            with self._ai_progress_env() as env:
                message = env["mail.message"].sudo().browse(message_id).exists()
                if message:
                    message.write({"body": body})
                    self._ai_note_listener(env, thread)._bus_send_store(
                        message,
                        {"body": message.body, "write_date": message.write_date},
                    )
        except Exception:
            _logger.warning(
                "Could not update a note of AI agent session %s",
                self.id,
                exc_info=True,
            )

    def _ai_drop_note(self, thread, message_id):
        """Remove a progress note, at once."""
        try:
            with self._ai_progress_env() as env:
                message = env["mail.message"].sudo().browse(message_id).exists()
                if message:
                    self._ai_note_listener(env, thread)._bus_send(
                        "mail.message/delete", {"message_ids": message.ids}
                    )
                    message.unlink()
        except Exception:
            _logger.warning(
                "Could not remove a note of AI agent session %s",
                self.id,
                exc_info=True,
            )

    def _ai_note_listener(self, env, thread):
        """Who is told about the changes of the notes: the conversation (its
        members), or the user of the session on the chatter of a document."""
        if thread._name == "discuss.channel":
            return env["discuss.channel"].sudo().browse(thread.id)
        return env["res.partner"].sudo().browse(self.user_id.partner_id.id)

    def _ai_close_pending_notes(self, thread):
        """Mark the progress notes left in progress as interrupted.

        Found in their own cursor: they were committed apart from the
        transaction of the failed iteration, which may not see them.
        """
        with self._ai_progress_env() as env:
            messages = (
                env["mail.message"]
                .sudo()
                .search(
                    [
                        ("model", "=", thread._name),
                        ("res_id", "=", thread.id),
                        ("author_id", "=", self.agent_id.user_id.partner_id.id),
                        ("message_type", "=", "notification"),
                        ("body", "ilike", PENDING_NOTE_CLASS),
                    ]
                )
            )
        for message in messages:
            text = html2plaintext(message.body or "").strip().lstrip("⏳").strip()
            if text == self.env._("Thinking..."):
                self._ai_drop_note(thread, message.id)
            else:
                self._ai_edit_note(
                    thread, message.id, self.env._("❌ %s (interrupted)", text)
                )

    def _post_note(self, thread, body):
        """Post a note of the agent, kept out of the AI history."""
        return thread.with_user(self.agent_id.user_id).message_post(
            body=body,
            message_type="notification",
            subtype_xmlid="mail.mt_note",
        )
