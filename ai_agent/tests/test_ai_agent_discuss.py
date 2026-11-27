# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command
from odoo.tools import mute_logger

from .common import AiAgentCase


def _answer(*args, **kwargs):
    return ("answer", 0, 0, 1)


class TestAiAgentConversations(AiAgentCase):
    def _start(self, body, user=None, document=None):
        agent = self.agent.with_user(user or self.human)
        result = agent.action_start_conversation(
            body,
            res_model=document._name if document else None,
            res_id=document.id if document else None,
        )
        return self.env["discuss.channel"].browse(result["channel_id"])

    # ------------------------------------------------------------
    # Channel
    # ------------------------------------------------------------

    def test_start_conversation(self):
        with self._patch_run(_answer) as run:
            channel = self._start("¿Qué tiempo hace mañana en Madrid?")
            run.assert_not_called()
            self.assertEqual(channel.channel_type, "ai_agent")
            self.assertEqual(channel.ai_agent_id, self.agent)
            self.assertEqual(
                channel.channel_partner_ids,
                self.human.partner_id | self.agent_user.partner_id,
            )
            session = self._session(channel)
            self.assertEqual(session.channel_id, channel)
            self.assertEqual(session.user_id, self.human)
            self.assertEqual(session.state, "queued")
            self.assertEqual(
                session.first_message, "¿Qué tiempo hace mañana en Madrid?"
            )
            self._run_worker()
        self.assertEqual(self._comments(channel)[-1].body, "<p>answer</p>")

    def test_start_conversation_requires_body(self):
        with self.assertRaises(UserError):
            self._start("  ")

    def test_conversations_have_their_own_history(self):
        calls = []

        def run(connection, **kwargs):
            calls.append(kwargs["messages"])
            return ("answer", 0, 0, 1)

        with self._patch_run(run):
            first = self._start("First topic")
            second = self._start("Second topic")
            self._run_worker()
        self.assertNotEqual(first, second)
        self.assertNotEqual(self._session(first), self._session(second))
        contents = sorted(c[-1]["content"] for c in calls)
        self.assertEqual(contents, ["First topic", "Second topic"])
        self.assertTrue(all(len(c) == 1 for c in calls))

    def test_conversation_is_private(self):
        channel = self._start("Hola")
        channel.with_user(self.human).read(["name"])
        with self.assertRaises(AccessError):
            channel.with_user(self.other_human).read(["name"])

    def test_context_document(self):
        self._add_tool("get_uid", "_ai_get_uid")
        document = self.env["ai.agent.test.document"].create({"name": "Doc 42"})
        records = []

        def run(connection, **kwargs):
            records.append(kwargs["record"])
            self.assertIn("Doc 42", kwargs["messages"][0]["content"])
            return ("answer", 0, 0, 1)

        with self._patch_run(run):
            channel = self._start("¿Cuál es el nombre?", document=document)
            self._run_worker()
        self.assertEqual(records, [document])
        self.assertEqual(records[0].env.uid, self.human.id)
        self.assertEqual(channel.ai_res_display_name, "Doc 42")
        self.assertEqual(self._session(channel).res_name, "Doc 42")
        self.assertFalse(self._comments(document))

    def test_context_document_not_readable(self):
        document = self.env["ai.agent.test.document"].create({"name": "Doc"})
        channel = self._create_agent_channel(document=document)
        self.env["ir.rule"].create(
            {
                "name": "no documents",
                "model_id": self.env["ir.model"]._get("ai.agent.test.document").id,
                "domain_force": "[(0, '=', 1)]",
            }
        )
        channel.invalidate_recordset()
        channel = channel.with_user(self.human)
        self.assertFalse(channel.ai_res_display_name)
        self.assertIsNone(channel._ai_get_context_document())

    def test_start_conversation_checks_document_access(self):
        document = self.env["ai.agent.test.document"].create({"name": "Doc"})
        self.env["ir.rule"].create(
            {
                "name": "no documents",
                "model_id": self.env["ir.model"]._get("ai.agent.test.document").id,
                "domain_force": "[(0, '=', 1)]",
            }
        )
        with self.assertRaises(AccessError):
            self._start("Hola", document=document)

    def test_inactive_agent_does_not_answer(self):
        channel = self._create_agent_channel()
        self.agent.active = False
        self._post(channel, "Hola")
        self.assertFalse(self._session(channel))

    def test_mention_on_document_still_enqueues(self):
        document = self.env["ai.agent.test.document"].create({"name": "Doc"})
        document.with_user(self.human).message_post(
            body="hola",
            partner_ids=[self.agent_user.partner_id.id],
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        session = self._session(document)
        self.assertEqual(session.state, "queued")
        self.assertEqual(session.res_name, "Doc")
        self.assertFalse(session.channel_id)

    # ------------------------------------------------------------
    # Direct messages
    # ------------------------------------------------------------

    def test_direct_message_with_agent_is_refused(self):
        with self.assertRaises(UserError):
            self.env["discuss.channel"].with_user(self.human).channel_get(
                [self.agent_user.partner_id.id]
            )
        with self.assertRaises(ValidationError):
            self.env["discuss.channel"].with_user(self.human).create(
                {
                    "name": "DM",
                    "channel_type": "chat",
                    "channel_partner_ids": [(4, self.agent_user.partner_id.id)],
                }
            )

    def test_direct_message_between_humans(self):
        channel = (
            self.env["discuss.channel"]
            .with_user(self.human)
            .channel_get([self.other_human.partner_id.id])
        )
        self.assertEqual(channel.channel_type, "chat")

    def test_direct_message_allowed_by_context(self):
        channel = (
            self.env["discuss.channel"]
            .with_user(self.human)
            .with_context(ai_agent_allow_dm=True)
            .channel_get([self.agent_user.partner_id.id])
        )
        self.assertEqual(channel.channel_type, "chat")

    def test_agents_are_not_in_conversation_searches(self):
        Partner = self.env["res.partner"].with_user(self.human)
        found = [p["id"] for p in Partner.im_search("Agent One").get("res.partner", [])]
        self.assertNotIn(self.agent_user.partner_id.id, found)
        found = [p["id"] for p in Partner.im_search("Human Two").get("res.partner", [])]
        self.assertIn(self.other_human.partner_id.id, found)

        result = Partner.search_for_channel_invite("Agent One")
        self.assertEqual(result["count"], 0)
        result = Partner.search_for_channel_invite("Human Two")
        self.assertEqual(result["count"], 1)

    def test_agents_are_still_mentionable(self):
        document = self.env["ai.agent.test.document"].create({"name": "Doc"})
        result = (
            self.env["res.partner"]
            .with_user(self.human)
            .get_mention_suggestions("Agent One", limit=8)
        )
        found = [p["id"] for p in result["res.partner"]]
        self.assertIn(self.agent_user.partner_id.id, found)
        self.assertTrue(document)

    # ------------------------------------------------------------
    # Sidebar and history
    # ------------------------------------------------------------

    def test_sidebar_data(self):
        document = self.env["ai.agent.test.document"].create({"name": "Doc 7"})
        with self._patch_run(_answer):
            first = self._start("Receta de paella")
            document.with_user(self.human).message_post(
                body="hola",
                partner_ids=[self.agent_user.partner_id.id],
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
            last = self._start("Tiempo en Madrid")
            self._start("Otro usuario", user=self.other_human)
        data = self.agent.with_user(self.human).get_sidebar_data()
        agent_data = next(a for a in data if a["id"] == self.agent.id)
        self.assertEqual(agent_data["partner_id"], self.agent_user.partner_id.id)
        sessions = agent_data["sessions"]
        self.assertEqual(len(sessions), 3)
        self.assertEqual(sessions[0]["channel_id"], last.id)
        self.assertEqual(sessions[0]["name"], "Tiempo en Madrid")
        chatter = sessions[1]
        self.assertFalse(chatter["channel_id"])
        self.assertEqual(chatter["res_model"], "ai.agent.test.document")
        self.assertEqual(chatter["res_id"], document.id)
        self.assertEqual(chatter["res_name"], "Doc 7")
        self.assertEqual(sessions[2]["channel_id"], first.id)

    def test_sidebar_limit(self):
        for index in range(7):
            self._start(f"Conversation {index}")
        data = self.agent.with_user(self.human).get_sidebar_data(limit=5)
        agent_data = next(a for a in data if a["id"] == self.agent.id)
        self.assertEqual(len(agent_data["sessions"]), 5)

    def test_search_sessions(self):
        document = self.env["ai.agent.test.document"].create({"name": "Arroz"})
        self._start("Receta de paella valenciana")
        self._start("Tiempo en Madrid")
        self._start("Sobre este documento", document=document)
        self._start("Paella para el otro", user=self.other_human)
        Agent = self.env["ai.agent"].with_user(self.human)
        result = Agent.search_sessions(self.agent.id, "paella")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["sessions"][0]["name"], "Receta de paella valenciana")
        result = Agent.search_sessions(self.agent.id, "arroz")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["sessions"][0]["res_name"], "Arroz")
        result = Agent.search_sessions(self.agent.id, "", offset=1, limit=1)
        self.assertEqual(result["count"], 3)
        self.assertEqual(len(result["sessions"]), 1)


class TestAiAgentTitle(AiAgentCase):
    generate_titles = True

    def _run_with(self, answers):
        """Patch the AI with an answer per call: turn answers and titles."""
        calls = []

        def run(connection, **kwargs):
            calls.append(kwargs)
            answer = answers[len(calls) - 1]
            if isinstance(answer, Exception):
                raise answer
            return (answer, 0, 0, 1)

        return calls, self._patch_run(run)

    def test_provisional_title(self):
        long_text = "¿Qué tiempo hace mañana en Madrid y en Barcelona por la tarde?"
        channel = self._create_agent_channel()
        self._post(channel, long_text)
        session = self._session(channel)
        self.assertTrue(session.name.startswith("¿Qué tiempo hace mañana"))
        self.assertLessEqual(len(session.name), 40)
        self.assertTrue(session.name.endswith("…"))

    def test_title_after_first_turn(self):
        calls, patcher = self._run_with(["Soleado", '"Tiempo en Madrid."', "Nublado"])
        channel = self._create_agent_channel()
        with patcher:
            self._post(channel, "¿Qué tiempo hace en Madrid?")
            self._run_worker()
            session = self._session(channel)
            self.assertEqual(session.name, "Tiempo en Madrid")
            self.assertEqual(channel.name, "Tiempo en Madrid")
            # The title is asked without tools, after the answer
            self.assertEqual(len(calls), 2)
            self.assertNotIn("tools", calls[1])
            self.assertEqual(
                [m["role"] for m in calls[1]["messages"]],
                ["system", "user", "assistant", "user"],
            )
            # Next turns never rename the session
            self._post(channel, "¿Y mañana?")
            self._run_worker()
        self.assertEqual(len(calls), 3)
        self.assertEqual(session.name, "Tiempo en Madrid")

    @mute_logger("odoo.addons.ai_agent.models.ai_agent_session")
    def test_title_failure_keeps_the_conversation(self):
        calls, patcher = self._run_with(["Soleado", ValueError("boom")])
        channel = self._create_agent_channel()
        with patcher:
            self._post(channel, "¿Qué tiempo hace en Madrid?")
            self._run_worker()
        session = self._session(channel)
        self.assertEqual(session.state, "idle")
        self.assertEqual(session.name, "¿Qué tiempo hace en Madrid?")
        self.assertEqual(self._comments(channel)[-1].body, "<p>Soleado</p>")
        self.assertFalse(self._notes(channel))

    def test_title_of_a_chatter_session(self):
        calls, patcher = self._run_with(["Hecho", "Nombre del documento"])
        document = self.env["ai.agent.test.document"].create({"name": "Doc"})
        with patcher:
            document.with_user(self.human).message_post(
                body="¿Cómo se llama?",
                partner_ids=[self.agent_user.partner_id.id],
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
            self._run_worker()
        self.assertEqual(self._session(document).name, "Nombre del documento")


class TestAiAgentChannelMembers(AiAgentCase):
    def test_agent_channel_is_not_a_chat(self):
        # An ai_agent conversation may hold the agent: only chats are refused
        channel = (
            self.env["discuss.channel"]
            .with_user(self.human)
            .create(
                {
                    "name": "Conversation",
                    "channel_type": "ai_agent",
                    "ai_agent_id": self.agent.id,
                    "channel_member_ids": [
                        Command.create({"partner_id": self.agent_user.partner_id.id})
                    ],
                }
            )
        )
        self.assertEqual(len(channel.channel_member_ids), 2)


class TestAiAgentViewContext(AiAgentCase):
    def _start(self, view_context, res_id=None):
        result = self.agent.with_user(self.human).action_start_conversation(
            "¿Cuántos hay?",
            res_model="ai.agent.test.document",
            res_id=res_id,
            view_context=view_context,
        )
        return self.env["discuss.channel"].browse(result["channel_id"])

    def test_list_view_context(self):
        records = []

        def run(connection, **kwargs):
            records.append(kwargs["record"])
            records.append(kwargs["messages"][0]["content"])
            return ("answer", 0, 0, 1)

        with self._patch_run(run):
            channel = self._start(
                {
                    "action_name": "Documents",
                    "view_type": "list",
                    "domain": [["name", "ilike", "Doc"]],
                    "group_by": ["name"],
                    "facets": ["Name: Doc"],
                    "unexpected": "dropped",
                }
            )
            self._run_worker()
        self.assertEqual(channel.ai_res_model, "ai.agent.test.document")
        self.assertFalse(channel.ai_res_id)
        self.assertNotIn("unexpected", channel.ai_context)
        self.assertEqual(self._session(channel).res_name, "Documents")
        record, prompt = records
        self.assertIsNone(record)
        self.assertIn('list view of "Documents"', prompt)
        self.assertIn("Name: Doc", prompt)
        self.assertIn("Grouped by: name", prompt)
        self.assertIn('[["name", "ilike", "Doc"]]', prompt)

    def test_form_view_context(self):
        document = self.env["ai.agent.test.document"].create({"name": "Doc 9"})
        prompts = []

        def run(connection, **kwargs):
            prompts.append((kwargs["record"], kwargs["messages"][0]["content"]))
            return ("answer", 0, 0, 1)

        with self._patch_run(run):
            self._start({"action_name": "Documents", "view_type": "form"}, document.id)
            self._run_worker()
        record, prompt = prompts[0]
        self.assertEqual(record, document)
        self.assertIn("Doc 9", prompt)
        self.assertIn('form view of "Documents"', prompt)

    def test_view_context_requires_model_access(self):
        self.env["ir.model.access"].search(
            [("model_id.model", "=", "ai.agent.test.document")]
        ).unlink()
        with self.assertRaises(AccessError):
            self._start({"view_type": "list"})
