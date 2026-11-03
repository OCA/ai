# Copyright 2026 SDi - Ángel Moya <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo_test_helper import FakeModelLoader
from psycopg2 import IntegrityError

from odoo.tests.common import TransactionCase

# Neither a missing required Many2one field nor a violated _sql_constraints
# is pre-validated/converted by the ORM here: both surface as a raw
# psycopg2.IntegrityError (NotNullViolation / UniqueViolation) once they
# hit the database.


class TestAiAgent(TransactionCase):
    def setUp(self):
        super().setUp()
        self.loader = FakeModelLoader(self.env, self.__module__)
        self.loader.backup_registry()
        from .fake_models import AiConnection

        self.loader.update_registry((AiConnection,))
        self.addCleanup(self.loader.restore_registry)

        self.connection = self.env["ai.connection"].create(
            {"name": "Test Connection", "kind": "demo"}
        )
        self.agent_user = self.env["res.users"].create(
            {
                "name": "Agent One",
                "login": "agent_one",
                "email": "agent_one@example.com",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )

    def test_agent_requires_user(self):
        with self.assertRaises(IntegrityError):
            self.env["ai.agent"].create(
                {
                    "name": "Agent",
                    "connection_id": self.connection.id,
                }
            )

    def test_agent_requires_connection(self):
        user = self.env["res.users"].create(
            {
                "name": "Agent Two",
                "login": "agent_two",
                "email": "agent_two@example.com",
                "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        with self.assertRaises(IntegrityError):
            self.env["ai.agent"].create(
                {
                    "name": "Agent",
                    "user_id": user.id,
                }
            )

    def test_agent_user_must_be_unique(self):
        self.env["ai.agent"].create(
            {
                "name": "Agent",
                "user_id": self.agent_user.id,
                "connection_id": self.connection.id,
            }
        )
        with self.assertRaises(IntegrityError):
            self.env["ai.agent"].create(
                {
                    "name": "Another Agent",
                    "user_id": self.agent_user.id,
                    "connection_id": self.connection.id,
                }
            )

    def test_agent_minimal_creation(self):
        agent = self.env["ai.agent"].create(
            {
                "name": "Agent",
                "user_id": self.agent_user.id,
                "connection_id": self.connection.id,
            }
        )
        self.assertFalse(agent.system_prompt)
        self.assertFalse(agent.tool_ids)
