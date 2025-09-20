# Copyright 2025 Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest import mock

from odoo.tests.common import TransactionCase


class TestProjectAiBridge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

        # Create necessary Project data
        cls.project = cls.env["project.project"].create(
            {
                "name": "Test Project",
                "description": "Test project description",
            }
        )

        cls.bridge_create = cls.env["ai.bridge"].create(
            {
                "name": "Project AI Bridge - Create",
                "description": "<p>Test bridge for project creation</p>",
                "model_id": cls.env.ref("project.model_project_project").id,
                "usage": "ai_thread_create",
                "url": "https://api.example.com/ai/project/create",
                "auth_type": "none",
                "payload_type": "record",
                "result_type": "none",
                "result_kind": "immediate",
                "field_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("project.field_project_project__name").id,
                            cls.env.ref("project.field_project_project__stage_id").id,
                        ],
                    )
                ],
            }
        )

        cls.bridge_write = cls.env["ai.bridge"].create(
            {
                "name": "Project AI Bridge - Update",
                "description": "<p>Test bridge for project updates</p>",
                "model_id": cls.env.ref("project.model_project_project").id,
                "usage": "ai_thread_write",
                "url": "https://api.example.com/ai/project/update",
                "auth_type": "none",
                "payload_type": "record",
                "result_type": "none",
                "result_kind": "immediate",
                "field_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("project.field_project_project__name").id,
                            cls.env.ref("project.field_project_project__stage_id").id,
                        ],
                    )
                ],
            }
        )

        cls.bridge_unlink = cls.env["ai.bridge"].create(
            {
                "name": "Project AI Bridge - Delete",
                "description": "<p>Test bridge for project deletion</p>",
                "model_id": cls.env.ref("project.model_project_project").id,
                "usage": "ai_thread_unlink",
                "url": "https://api.example.com/ai/project/delete",
                "auth_type": "none",
                "payload_type": "none",
                "result_type": "none",
                "result_kind": "immediate",
            }
        )

        # Create bridges for tasks
        cls.bridge_task_create = cls.env["ai.bridge"].create(
            {
                "name": "Task AI Bridge - Create",
                "description": "<p>Test bridge for task creation</p>",
                "model_id": cls.env.ref("project.model_project_task").id,
                "usage": "ai_thread_create",
                "url": "https://api.example.com/ai/task/create",
                "auth_type": "none",
                "payload_type": "record",
                "result_type": "none",
                "result_kind": "immediate",
                "field_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("project.field_project_task__name").id,
                            cls.env.ref("project.field_project_task__stage_id").id,
                        ],
                    )
                ],
            }
        )

        cls.bridge_task_write = cls.env["ai.bridge"].create(
            {
                "name": "Task AI Bridge - Update",
                "description": "<p>Test bridge for task updates</p>",
                "model_id": cls.env.ref("project.model_project_task").id,
                "usage": "ai_thread_write",
                "url": "https://api.example.com/ai/task/update",
                "auth_type": "none",
                "payload_type": "record",
                "result_type": "none",
                "result_kind": "immediate",
                "field_ids": [
                    (
                        6,
                        0,
                        [
                            cls.env.ref("project.field_project_task__name").id,
                            cls.env.ref("project.field_project_task__stage_id").id,
                        ],
                    )
                ],
            }
        )

        cls.bridge_task_unlink = cls.env["ai.bridge"].create(
            {
                "name": "Task AI Bridge - Delete",
                "description": "<p>Test bridge for task deletion</p>",
                "model_id": cls.env.ref("project.model_project_task").id,
                "usage": "ai_thread_unlink",
                "url": "https://api.example.com/ai/task/delete",
                "auth_type": "none",
                "payload_type": "none",
                "result_type": "none",
                "result_kind": "immediate",
            }
        )

    def test_project_create_bridge(self):
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Project created"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_create.id)]
                ),
            )
            project = self.env["project.project"].create(
                {
                    "name": "Test Project for Bridge",
                    "description": "Test project description for bridge",
                }
            )
            executions = self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge_create.id)]
            )
            self.assertEqual(len(executions), 1)
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "https://api.example.com/ai/project/create")
            record = kwargs["json"].get("record", {})
            self.assertEqual(record.get("id"), project.id)
            self.assertEqual(record.get("name"), "Test Project for Bridge")

    def test_project_write_bridge(self):
        self.bridge_create.active = False
        project = self.env["project.project"].create(
            {
                "name": "Test Project for Update",
                "description": "Test project description for update",
            }
        )
        self.bridge_create.active = True
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Project updated"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_write.id)]
                ),
            )
            project.write(
                {
                    "name": "Updated Project",
                    "description": "Updated project description",
                }
            )
            executions = self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge_write.id)]
            )
            self.assertEqual(len(executions), 1)
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "https://api.example.com/ai/project/update")
            record = kwargs["json"].get("record", {})
            self.assertEqual(record.get("id"), project.id)
            self.assertEqual(record.get("name"), "Updated Project")

    def test_project_unlink_bridge(self):
        self.bridge_create.active = False
        project = self.env["project.project"].create(
            {
                "name": "Test Project for Deletion",
                "description": "Test project description for deletion",
            }
        )
        self.bridge_create.active = True
        project_id = project.id
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Project deleted"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_unlink.id)]
                ),
            )
            project.unlink()
            executions = self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge_unlink.id)]
            )
            self.assertEqual(len(executions), 1)
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "https://api.example.com/ai/project/delete")
            self.assertEqual(kwargs["json"].get("_id", False), project_id)

    def test_all_bridges_together(self):
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Success"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_create.id)]
                ),
            )
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_write.id)]
                ),
            )
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_unlink.id)]
                ),
            )
            project = self.env["project.project"].create(
                {
                    "name": "Complete Test Project",
                    "description": "Complete test project description",
                }
            )
            project.write(
                {
                    "name": "Updated Complete Test Project",
                    "description": "Updated complete test project description",
                }
            )
            project.unlink()

            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_create.id)]
                ),
            )
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_write.id)]
                ),
            )
            self.assertEqual(
                1,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_unlink.id)]
                ),
            )

    def test_task_create_bridge(self):
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Task created"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_task_create.id)]
                ),
            )
            task = self.env["project.task"].create(
                {
                    "name": "Test Task for Bridge",
                    "description": "Test task description for bridge",
                    "project_id": self.project.id,
                }
            )
            executions = self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge_task_create.id)]
            )
            self.assertEqual(len(executions), 1)
            args, kwargs = mock_post.call_args
            self.assertIn(
                args[0],
                [
                    "https://api.example.com/ai/task/create",
                    "https://api.example.com/ai/task/update",
                ],
            )
            record = kwargs["json"].get("record", {})
            self.assertEqual(record.get("id"), task.id)
            self.assertEqual(record.get("name"), "Test Task for Bridge")

    def test_task_write_bridge(self):
        self.bridge_task_create.active = False
        task = self.env["project.task"].create(
            {
                "name": "Test Task for Update",
                "description": "Test task description for update",
                "project_id": self.project.id,
            }
        )
        self.bridge_task_create.active = True
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Task updated"}
            self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge_task_write.id)]
            ).unlink()
            task.write(
                {
                    "name": "Updated Task",
                    "description": "Updated task description",
                }
            )
            executions = self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge_task_write.id)]
            )
            self.assertGreaterEqual(len(executions), 1)
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "https://api.example.com/ai/task/update")
            record = kwargs["json"].get("record", {})
            self.assertEqual(record.get("id"), task.id)
            self.assertEqual(record.get("name"), "Updated Task")

    def test_task_unlink_bridge(self):
        self.bridge_task_create.active = False
        task = self.env["project.task"].create(
            {
                "name": "Test Task for Deletion",
                "description": "Test task description for deletion",
                "project_id": self.project.id,
            }
        )
        self.bridge_task_create.active = True
        task_id = task.id
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Task deleted"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_task_unlink.id)]
                ),
            )
            task.unlink()
            executions = self.env["ai.bridge.execution"].search(
                [("ai_bridge_id", "=", self.bridge_task_unlink.id)]
            )
            self.assertEqual(len(executions), 1)
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "https://api.example.com/ai/task/delete")
            self.assertEqual(kwargs["json"].get("_id", False), task_id)

    def test_all_task_bridges_together(self):
        with mock.patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"message": "Success"}
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_task_create.id)]
                ),
            )
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_task_write.id)]
                ),
            )
            self.assertEqual(
                0,
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_task_unlink.id)]
                ),
            )
            task = self.env["project.task"].create(
                {
                    "name": "Complete Test Task",
                    "description": "Complete test task description",
                    "project_id": self.project.id,
                }
            )
            task.write(
                {
                    "name": "Updated Complete Test Task",
                    "description": "Updated complete test task description",
                }
            )
            task.unlink()

            self.assertGreaterEqual(
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_task_create.id)]
                ),
                1,
            )
            self.assertGreaterEqual(
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_task_write.id)]
                ),
                1,
            )
            self.assertGreaterEqual(
                self.env["ai.bridge.execution"].search_count(
                    [("ai_bridge_id", "=", self.bridge_task_unlink.id)]
                ),
                1,
            )
