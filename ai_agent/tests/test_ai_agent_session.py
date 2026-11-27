# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tools import config, mute_logger

from .common import AiAgentCase


class TestAiAgentSession(AiAgentCase):
    def test_get_or_create_session_singleton(self):
        Session = self.env["ai.agent.session"]
        session1 = Session._get_or_create_session(
            self.agent, self.human, "discuss.channel", 1
        )
        session2 = Session._get_or_create_session(
            self.agent, self.human, "discuss.channel", 1
        )
        self.assertEqual(session1, session2)
        session3 = Session._get_or_create_session(
            self.agent, self.human, "discuss.channel", 2
        )
        self.assertNotEqual(session1, session3)

    def test_agent_channel_triggers_reply(self):
        channel = self._create_agent_channel()
        channel.with_user(self.human).message_post(
            body="Hola agente",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self._run_worker()
        messages = self._comments(channel)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].author_id, self.human.partner_id)
        self.assertEqual(messages[1].author_id, self.agent_user.partner_id)

        session = self.env["ai.agent.session"].search(
            [
                ("agent_id", "=", self.agent.id),
                ("user_id", "=", self.human.id),
                ("res_model", "=", "discuss.channel"),
                ("res_id", "=", channel.id),
            ]
        )
        self.assertTrue(session)

    def test_agent_channel_reply_does_not_recurse(self):
        channel = self._create_agent_channel()
        channel.with_user(self.human).message_post(
            body="Hola agente",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self._run_worker()
        # Posting once must not cascade beyond the single auto-reply.
        self.assertEqual(len(self._comments(channel)), 2)

    def test_mention_on_document_triggers_reply(self):
        document = self.env["ai.agent.test.document"].create({"name": "Doc"})
        document.with_user(self.human).message_post(
            body="hola",
            partner_ids=[self.agent_user.partner_id.id],
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self._run_worker()
        messages = self._comments(document)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].author_id, self.human.partner_id)
        self.assertEqual(messages[1].author_id, self.agent_user.partner_id)

        session = self.env["ai.agent.session"].search(
            [
                ("agent_id", "=", self.agent.id),
                ("user_id", "=", self.human.id),
                ("res_model", "=", "ai.agent.test.document"),
                ("res_id", "=", document.id),
            ]
        )
        self.assertTrue(session)

    def test_document_message_without_mention_does_not_trigger(self):
        document = self.env["ai.agent.test.document"].create({"name": "Doc"})
        document.with_user(self.human).message_post(
            body="hola",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self._run_worker()
        self.assertEqual(len(self._comments(document)), 1)
        session = self.env["ai.agent.session"].search(
            [("agent_id", "=", self.agent.id), ("user_id", "=", self.human.id)]
        )
        self.assertFalse(session)

    def test_tool_executes_as_message_author(self):
        model = self.env["ir.model"]._get("ai.agent.test.tool")
        tool = self.env["ai.tool"].create(
            {
                "name": "get_uid",
                "description": "Return the current user id",
                "model_id": model.id,
                "function_name": "_ai_get_uid",
                "kind": "generic",
            }
        )
        self.agent.tool_ids = [(6, 0, [tool.id])]
        document = self.env["ai.agent.test.document"].create({"name": "Doc"})
        document.with_user(self.human).message_post(
            body="get_uid",
            partner_ids=[self.agent_user.partner_id.id],
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self._run_worker()
        reply = self._comments(document)[-1]
        self.assertIn(f'"uid": {self.human.id}', reply.body)
        self.assertNotIn(f'"uid": {self.agent_user.id}', reply.body)

    def test_get_tool_record(self):
        session = self.env["ai.agent.session"]._get_or_create_session(
            self.agent, self.human, "discuss.channel", 1
        )
        document = self.env["ai.agent.test.document"].create({"name": "Doc"})
        self.assertEqual(session._get_tool_record(document), document)
        channel = self._create_agent_channel()
        self.assertIsNone(session._get_tool_record(channel))
        channel = self._create_agent_channel(document=document)
        self.assertEqual(session._get_tool_record(channel), document)

    def test_session_access_restricted_to_owner(self):
        session = self.env["ai.agent.session"]._get_or_create_session(
            self.agent, self.human, "discuss.channel", 1
        )
        session.with_user(self.human).read(["name"])
        with self.assertRaises(AccessError):
            session.with_user(self.other_human).read(["name"])
        session.with_user(self.admin_human).read(["name"])

    # ------------------------------------------------------------
    # Asynchronous execution
    # ------------------------------------------------------------

    def test_post_only_enqueues(self):
        channel = self._create_agent_channel()
        with self._patch_run(lambda *a, **k: ("answer", 0, 0, 1)) as run:
            message = self._post(channel, "Hola agente")
            run.assert_not_called()
            session = self._session(channel)
            self.assertEqual(session.state, "queued")
            self.assertEqual(session.pending_message_id, message)
            self.assertEqual(len(self._comments(channel)), 1)
            self._run_worker()
            run.assert_called_once()
        self.assertEqual(session.state, "idle")
        self.assertEqual(session.processed_message_id, message)
        self.assertFalse(session.claimed_at)
        self.assertEqual(self._comments(channel)[-1].body, "<p>answer</p>")

    def test_system_prompt_goes_first(self):
        self.agent.system_prompt = "Be nice"
        channel = self._create_agent_channel()
        with self._patch_run(lambda *a, **k: ("answer", 0, 0, 1)) as run:
            self._post(channel, "Hola agente")
            self._run_worker()
        messages = run.call_args.kwargs["messages"]
        self.assertEqual(messages[0], {"role": "system", "content": "Be nice"})
        self.assertEqual(messages[1], {"role": "user", "content": "Hola agente"})
        self.assertTrue(run.call_args.kwargs["tool_activity"])

    def test_tool_without_access_fails_as_the_user(self):
        self._add_tool("count_params", "_ai_count_params")
        document = self.env["ai.agent.test.document"].create({"name": "Doc"})
        document.with_user(self.human).message_post(
            body="count_params",
            partner_ids=[self.agent_user.partner_id.id],
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self._run_worker()
        # The error is answered to the AI (the demo client echoes it)
        self.assertIn("AccessError", self._comments(document)[-1].body)
        self.assertIn("count_params failed", self._notes(document)[-1].body)
        self.assertEqual(self._session(document).state, "idle")

    def test_messages_posted_while_running_rerun_the_turn(self):
        channel = self._create_agent_channel()
        calls = []

        def run(connection, **kwargs):
            calls.append(kwargs["messages"])
            if len(calls) == 1:
                # The user writes again while the agent is answering
                self.assertEqual(self._session(channel).state, "running")
                self._post(channel, "Second")
            return (f"answer {len(calls)}", 0, 0, 1)

        with self._patch_run(run):
            self._post(channel, "First")
            self._run_worker()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][-2]["content"], "Second")
        self.assertEqual(
            [m.body for m in self._comments(channel)],
            ["<p>First</p>", "<p>Second</p>", "<p>answer 1</p>", "<p>answer 2</p>"],
        )
        self.assertEqual(self._session(channel).state, "idle")

    @mute_logger("odoo.addons.ai_agent.models.ai_agent_session")
    def test_error_keeps_user_message_and_is_notified(self):
        channel = self._create_agent_channel()

        def run(connection, **kwargs):
            # Uncommitted work of the failing turn is discarded
            kwargs["on_step"]({"type": "tool_call", "tool": "x", "activity": None})
            raise ValueError("boom")

        with self._patch_run(run):
            self._post(channel, "Hola agente")
            self._run_worker()
        session = self._session(channel)
        self.assertEqual(session.state, "error")
        self.assertEqual(session.error_message, "boom")
        self.assertEqual(len(self._comments(channel)), 1)
        notes = self._notes(channel)
        self.assertEqual(len(notes), 1)
        self.assertIn("boom", notes.body)

    @mute_logger("odoo.addons.ai_agent.models.ai_agent_session")
    def test_error_session_is_requeued_by_a_new_message(self):
        channel = self._create_agent_channel()
        with self._patch_run(ValueError("boom")):
            self._post(channel, "Hola agente")
            self._run_worker()
        session = self._session(channel)
        self.assertEqual(session.state, "error")
        with self._patch_run(lambda *a, **k: ("answer", 0, 0, 1)):
            self._post(channel, "Again")
            self.assertEqual(session.state, "queued")
            self.assertFalse(session.error_message)
            self._run_worker()
        self.assertEqual(session.state, "idle")
        self.assertEqual(self._comments(channel)[-1].body, "<p>answer</p>")

    @mute_logger("odoo.addons.ai_agent.models.ai_agent_session")
    def test_stale_running_session_is_recovered(self):
        channel = self._create_agent_channel()
        session = self.env["ai.agent.session"]._get_or_create_session(
            self.agent, self.human, "discuss.channel", channel.id
        )
        session.write(
            {
                "state": "running",
                "claimed_at": fields.Datetime.now() - timedelta(hours=1),
            }
        )
        session._ai_start_turn()
        fresh = self.env["ai.agent.session"]._get_or_create_session(
            self.agent, self.other_human, "discuss.channel", channel.id
        )
        fresh.write({"state": "running", "claimed_at": fields.Datetime.now()})
        with patch.dict(
            config.options,
            {"limit_time_real_cron": -1, "limit_time_real": 120},
        ):
            self._run_worker_once()
        self.assertEqual(session.state, "error")
        self.assertIn("120 seconds", session.error_message)
        self.assertIn("120 seconds", self._notes(channel)[-1].body)
        self.assertFalse(session.turn_ids)
        self.assertEqual(fresh.state, "running")

    # ------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------

    def test_tool_note_with_default_text(self):
        self._add_tool("get_uid", "_ai_get_uid")
        document = self.env["ai.agent.test.document"].create({"name": "Doc"})
        document.with_user(self.human).message_post(
            body="get_uid",
            partner_ids=[self.agent_user.partner_id.id],
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self._run_worker()
        notes = self._notes(document)
        self.assertEqual(len(notes), 1)
        self.assertIn("Running get_uid...", notes.body)
        self.assertLess(notes.id, self._comments(document)[-1].id)

    def test_tool_note_with_activity(self):
        self._add_tool("get_uid", "_ai_get_uid")
        document = self.env["ai.agent.test.document"].create({"name": "Doc"})
        document.with_user(self.human).message_post(
            body='call:get_uid {"activity": "Leyendo el usuario..."}',
            partner_ids=[self.agent_user.partner_id.id],
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self._run_worker()
        self.assertIn("Leyendo el usuario...", self._notes(document).body)
        # activity never reaches the tool, which takes no arguments
        self.assertIn(f'"uid": {self.human.id}', self._comments(document)[-1].body)

    def test_notes_are_not_in_history(self):
        self._add_tool("get_uid", "_ai_get_uid")
        document = self.env["ai.agent.test.document"].create({"name": "Doc"})
        document.with_user(self.human).message_post(
            body="get_uid",
            partner_ids=[self.agent_user.partner_id.id],
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self._run_worker()
        self.assertTrue(self._notes(document))
        history = self._session(document)._build_history_from_thread(document)
        self.assertEqual([h["role"] for h in history], ["user", "assistant"])

    def test_reasoning_note_is_collapsible(self):
        channel = self._create_agent_channel()

        def run(connection, **kwargs):
            kwargs["on_step"]({"type": "iteration", "reasoning": "a < b"})
            return ("answer", 0, 0, 1)

        with self._patch_run(run):
            self._post(channel, "Hola agente")
            self._run_worker()
        note = self._notes(channel)
        self.assertEqual(len(note), 1)
        self.assertIn("<details>", note.body)
        self.assertIn("<summary>Reasoning</summary>", note.body)
        self.assertIn("a &lt; b", note.body)

    def test_answer_markdown_is_rendered(self):
        channel = self._create_agent_channel()
        answer = "Es **París**.\n\n- uno\n- dos\n\n<script>alert(1)</script>"
        with self._patch_run(lambda *a, **k: (answer, 0, 0, 1)):
            self._post(channel, "Hola agente")
            self._run_worker()
        body = self._comments(channel)[-1].body
        self.assertIn("<strong>París</strong>", body)
        self.assertIn("<li>uno</li>", body)
        self.assertNotIn("<script>", body)

    # ------------------------------------------------------------
    # One iteration per worker run
    # ------------------------------------------------------------

    def test_each_iteration_runs_in_its_own_worker_run(self):
        self._add_tool("get_uid", "_ai_get_uid")
        channel = self._create_agent_channel()
        self._post(channel, "get_uid")
        session = self._session(channel)
        self._run_worker_once()
        # The tool ran: the rest of the turn waits for the next run
        self.assertEqual(session.state, "queued")
        self.assertEqual(len(self._comments(channel)), 1)
        self.assertEqual(len(self._notes(channel)), 1)
        turn = session.turn_ids
        self.assertEqual(turn.iteration, 2)
        self.assertEqual([m["role"] for m in turn.messages], ["assistant", "tool"])
        self._run_worker_once()
        self.assertEqual(session.state, "idle")
        self.assertFalse(session.turn_ids)
        self.assertIn(f'"uid": {self.human.id}', self._comments(channel)[-1].body)
        # The tool ran only once
        self.assertEqual(len(self._notes(channel)), 1)

    def test_next_iteration_goes_on_from_the_turn(self):
        channel = self._create_agent_channel()
        calls = []

        def run(connection, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                kwargs["next_iteration"](
                    {
                        "messages": kwargs["messages"]
                        + [
                            {"role": "assistant", "content": "", "tool_calls": []},
                            {"role": "tool", "content": '{"done": true}'},
                        ],
                        "iteration": 2,
                    }
                )
                return None
            return ("answer", 0, 0, 2)

        with self._patch_run(run):
            self._post(channel, "Hola agente")
            self._run_worker()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["iteration"], 1)
        self.assertEqual(calls[1]["iteration"], 2)
        messages = calls[1]["messages"]
        self.assertEqual(messages[-1], {"role": "tool", "content": '{"done": true}'})
        self.assertEqual(messages[-3], {"role": "user", "content": "Hola agente"})
        self.assertEqual(self._comments(channel)[-1].body, "<p>answer</p>")

    def test_new_message_between_iterations_is_answered_after(self):
        self._add_tool("get_uid", "_ai_get_uid")
        channel = self._create_agent_channel()
        self._post(channel, "get_uid")
        self._run_worker_once()
        self._post(channel, "Second")
        Connection = self.env.registry["ai.connection"]
        with patch.object(
            Connection, "_run", autospec=True, side_effect=Connection._run
        ) as run:
            self._run_worker()
        # The turn in progress goes on without the new message, the next one
        # has it
        first, second = (call.kwargs["messages"] for call in run.call_args_list)
        self.assertNotIn("Second", [m.get("content") for m in first])
        self.assertIn("Second", [m.get("content") for m in second])
        comments = self._comments(channel)
        self.assertEqual(
            [c.author_id for c in comments],
            [
                self.human.partner_id,
                self.human.partner_id,
                self.agent_user.partner_id,
                self.agent_user.partner_id,
            ],
        )
        self.assertIn(f'"uid": {self.human.id}', comments[2].body)
        self.assertEqual(self._session(channel).state, "idle")

    def test_stale_seconds_follow_the_cron_time_limit(self):
        Session = self.env["ai.agent.session"]
        with patch.dict(
            config.options,
            {"limit_time_real_cron": -1, "limit_time_real": 120},
        ):
            self.assertEqual(Session._cron_time_limit(), 120)
            self.assertEqual(Session._stale_seconds(), 180)
        with patch.dict(
            config.options,
            {"limit_time_real_cron": 0, "limit_time_real": 120},
        ):
            self.assertIsNone(Session._cron_time_limit())
            self.assertEqual(Session._stale_seconds(), 900)

    def test_sessions_take_turns_between_iterations(self):
        self._add_tool("get_uid", "_ai_get_uid")
        first = self._create_agent_channel()
        second = self._create_agent_channel()
        self._post(first, "get_uid")
        self._post(second, "get_uid")
        # Same transaction in tests: make the queue order explicit
        self.env.cr.execute(
            "UPDATE ai_agent_session SET write_date = write_date - interval '1 minute'"
            " WHERE id = %s",
            (self._session(first).id,),
        )
        self.env.invalidate_all()
        self._run_worker_once()
        self.assertEqual(self._session(first).state, "queued")
        self.assertEqual(self._session(second).state, "queued")
        self.assertEqual(self._session(first).turn_ids.iteration, 2)
        self.assertFalse(self._session(second).turn_ids)
        # Back in the queue later than the second one (now() is the same for
        # the whole test transaction)
        self.env.cr.execute(
            "UPDATE ai_agent_session SET write_date = write_date + interval '1 minute'"
            " WHERE id = %s",
            (self._session(first).id,),
        )
        self.env.invalidate_all()
        self._run_worker_once()
        # The second session ran its first iteration before the first one
        # went on
        self.assertEqual(self._session(second).turn_ids.iteration, 2)
        self.assertEqual(self._session(first).turn_ids.iteration, 2)

    # ------------------------------------------------------------
    # Live progress notes
    # ------------------------------------------------------------

    def test_thinking_note_becomes_the_reasoning(self):
        channel = self._create_agent_channel()
        seen = {}

        def run(connection, **kwargs):
            kwargs["on_step"]({"type": "llm_call", "iteration": 1})
            thinking = self._notes(channel)
            seen["thinking"] = (thinking.id, thinking.body)
            kwargs["on_step"]({"type": "iteration", "reasoning": "Pienso"})
            return ("answer", 0, 0, 1)

        with self._patch_run(run):
            self._post(channel, "Hola agente")
            self._run_worker()
        note_id, body = seen["thinking"]
        self.assertIn("Thinking...", body)
        self.assertIn("o_ai_agent_pending", body)
        note = self._notes(channel)
        # The same note, now the collapsible reasoning
        self.assertEqual(note.id, note_id)
        self.assertIn("<summary>Reasoning</summary>", note.body)
        self.assertIn("Pienso", note.body)
        self.assertNotIn("o_ai_agent_pending", note.body)

    def test_thinking_note_removed_without_reasoning(self):
        channel = self._create_agent_channel()
        self._post(channel, "Hola agente")
        self._run_worker()
        self.assertFalse(self._notes(channel))

    def test_tool_note_is_ticked_when_done(self):
        self._add_tool("get_uid", "_ai_get_uid")
        channel = self._create_agent_channel()
        seen = []
        on_step = self.env.registry["ai.agent.session"]._on_step

        def spy(session, thread, step, progress=None):
            result = on_step(session, thread, step, progress)
            if step["type"] == "tool_call":
                seen.append(self._notes(channel)[-1].body)
            return result

        with patch.object(
            self.env.registry["ai.agent.session"],
            "_on_step",
            autospec=True,
            side_effect=spy,
        ):
            self._post(channel, "get_uid")
            self._run_worker()
        self.assertIn("⏳ Running get_uid...", seen[0])
        self.assertIn("o_ai_agent_pending", seen[0])
        note = self._notes(channel)
        self.assertEqual(len(note), 1)
        self.assertIn("✓ Running get_uid...", note.body)
        self.assertNotIn("o_ai_agent_pending", note.body)

    @mute_logger("odoo.addons.ai_agent.models.ai_agent_session")
    def test_pending_notes_are_closed_when_failing(self):
        channel = self._create_agent_channel()
        session = self.env["ai.agent.session"]._get_or_create_session(
            self.agent, self.human, "discuss.channel", channel.id
        )
        # Notes left in progress by an iteration that died
        session._ai_note(channel, session._ai_pending_body("Thinking..."))
        session._ai_note(channel, session._ai_pending_body("⏳ Creando pedidos..."))
        session._fail("boom")
        bodies = self._notes(channel).mapped("body")
        self.assertEqual(len(bodies), 2)
        self.assertIn("❌ Creando pedidos... (interrupted)", bodies[0])
        self.assertIn("boom", bodies[1])
        self.assertFalse([b for b in bodies if "o_ai_agent_pending" in b])
