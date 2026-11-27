# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo_test_helper import FakeModelLoader

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestAiAgentTour(HttpCase):
    def setUp(self):
        super().setUp()
        self.loader = FakeModelLoader(self.env, self.__module__)
        self.loader.backup_registry()
        from .fake_models import AiConnection

        self.loader.update_registry((AiConnection,))
        self.addCleanup(self.loader.restore_registry)
        connection = self.env["ai.connection"].create(
            {"name": "Tour Connection", "kind": "demo"}
        )
        agent_user = self.env["res.users"].create(
            {
                "name": "Tour Agent",
                "login": "tour_agent",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        self.env["ai.agent"].create(
            {
                "name": "Tour Agent",
                "user_id": agent_user.id,
                "connection_id": connection.id,
            }
        )

    def test_conversation_tour(self):
        Session = self.env.registry["ai.agent.session"]
        enqueue = Session._enqueue_turn

        def enqueue_and_answer(session, message):
            # No cron runs during the tests: answer right away
            enqueue(session, message)
            session.env["ai.agent.session"]._cron_process_queue()

        with (
            patch.object(Session, "_enqueue_turn", enqueue_and_answer),
            patch.object(
                Session, "_ai_generate_title", return_value="Capital de Francia"
            ),
        ):
            self.start_tour(
                "/odoo/discuss", "ai_agent_conversation_tour", login="admin"
            )
