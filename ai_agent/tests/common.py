# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo_test_helper import FakeModelLoader

from odoo.fields import Command
from odoo.tests.common import TransactionCase


class AiAgentCase(TransactionCase):
    generate_titles = False

    def setUp(self):
        super().setUp()
        self.loader = FakeModelLoader(self.env, self.__module__)
        self.loader.backup_registry()
        from .fake_models import AiAgentTestDocument, AiAgentTestTool, AiConnection

        self.loader.update_registry(
            (AiConnection, AiAgentTestTool, AiAgentTestDocument)
        )
        self.addCleanup(self.loader.restore_registry)
        if self.generate_titles is False:
            title_patch = patch.object(
                self.env.registry["ai.agent.session"],
                "_ai_generate_title",
                return_value=False,
            )
            title_patch.start()
            self.addCleanup(title_patch.stop)
        self.env["ir.model.access"].create(
            {
                "name": "ai_agent_test_document_all",
                "model_id": self.env["ir.model"]._get("ai.agent.test.document").id,
                "group_id": self.env.ref("base.group_user").id,
                "perm_read": 1,
                "perm_write": 1,
                "perm_create": 1,
                "perm_unlink": 1,
            }
        )

        self.connection = self.env["ai.connection"].create(
            {"name": "Test Connection", "kind": "demo"}
        )
        self.agent_user = self.env["res.users"].create(
            {
                "name": "Agent One",
                "login": "agent_one_session",
                "email": "agent_one_session@example.com",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        self.agent = self.env["ai.agent"].create(
            {
                "name": "Agent",
                "user_id": self.agent_user.id,
                "connection_id": self.connection.id,
            }
        )
        self.human = self.env["res.users"].create(
            {
                "name": "Human One",
                "login": "human_one",
                "email": "human_one@example.com",
                # ai.tool._execute_tool() reads tool.model_id.model, which
                # requires read access on ir.model. Plain base.group_user
                # does not grant that (only group_erp_manager/group_system
                # do), so a human expected to trigger tool-using agents
                # needs it too.
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("base.group_erp_manager").id,
                        ],
                    )
                ],
            }
        )
        self.other_human = self.env["res.users"].create(
            {
                "name": "Human Two",
                "login": "human_two",
                "email": "human_two@example.com",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        self.admin_human = self.env["res.users"].create(
            {
                "name": "Admin",
                "login": "admin_human",
                "email": "admin_human@example.com",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("base.group_system").id,
                        ],
                    )
                ],
            }
        )

    def _create_agent_channel(self, user=None, document=None):
        values = {
            "name": "Conversation",
            "channel_type": "ai_agent",
            "ai_agent_id": self.agent.id,
            "channel_member_ids": [
                Command.create({"partner_id": self.agent_user.partner_id.id})
            ],
        }
        if document:
            values.update(ai_res_model=document._name, ai_res_id=document.id)
        return self.env["discuss.channel"].with_user(user or self.human).create(values)

    def _run_worker(self):
        """Run the cron worker, then again as long as it re-triggers itself."""
        Session = self.env["ai.agent.session"]
        for _run in range(20):
            Session._cron_process_queue()
            if not Session.search_count([("state", "=", "queued")]):
                return

    def _run_worker_once(self):
        self.env["ai.agent.session"]._cron_process_queue()

    def _comments(self, thread):
        return thread.message_ids.filtered(
            lambda m: m.message_type == "comment"
        ).sorted("id")

    def _post(self, thread, body, user=None):
        return thread.with_user(user or self.human).message_post(
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )

    def _session(self, thread):
        return self.env["ai.agent.session"].search(
            [
                ("agent_id", "=", self.agent.id),
                ("res_model", "=", thread._name),
                ("res_id", "=", thread.id),
            ]
        )

    def _notes(self, thread):
        return thread.message_ids.filtered(
            lambda m: m.message_type == "notification"
            and m.author_id == self.agent_user.partner_id
        ).sorted("id")

    def _patch_run(self, side_effect):
        return patch.object(
            self.env.registry["ai.connection"],
            "_run",
            autospec=True,
            side_effect=side_effect,
        )

    def _add_tool(self, name, function_name):
        tool = self.env["ai.tool"].create(
            {
                "name": name,
                "description": name,
                "model_id": self.env["ir.model"]._get("ai.agent.test.tool").id,
                "function_name": function_name,
                "kind": "generic",
            }
        )
        self.agent.tool_ids = [(4, tool.id)]
        return tool
