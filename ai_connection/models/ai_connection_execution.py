# Copyright 2026 SDi <amoya@sdi.es>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class AiConnectionExecution(models.Model):
    _name = "ai.connection.execution"
    _description = "AI Connection Execution"
    _order = "id desc"

    connection_id = fields.Many2one(
        "ai.connection", string="Connection", required=True, ondelete="cascade"
    )
    name = fields.Char(default="AI Execution")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("running", "Running"),
            ("paused", "Paused"),
            ("pending_tool_approval", "Pending Tool Approval"),
            ("done", "Done"),
            ("failed", "Failed"),
        ],
        default="draft",
        required=True,
    )

    prompt = fields.Text(string="Initial Prompt")
    system_prompt = fields.Text()
    messages_json = fields.Json(string="Messages History", default=list)
    tool_ids = fields.Many2many("ai.tool", string="Available Tools")

    res_model = fields.Char(string="Related Model")
    res_id = fields.Integer(string="Related ID")

    max_iterations = fields.Integer(default=50)
    current_iteration = fields.Integer(default=0)

    prompt_tokens = fields.Integer(default=0)
    completion_tokens = fields.Integer(default=0)
    total_tokens = fields.Integer(compute="_compute_total_tokens", store=True)

    result_content = fields.Text()
    error_message = fields.Text()

    debug = fields.Boolean(string="Debug Mode", default=False)
    stepwise = fields.Boolean(string="Step-by-Step Mode", default=False)
    stream = fields.Boolean(string="Stream Mode", default=False)
    stream_batch_size = fields.Integer(default=40)

    iteration_ids = fields.One2many(
        "ai.connection.execution.iteration", "execution_id", string="Iterations"
    )

    @api.depends("prompt_tokens", "completion_tokens")
    def _compute_total_tokens(self):
        for rec in self:
            rec.total_tokens = rec.prompt_tokens + rec.completion_tokens

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.messages_json:
                extracted = []
                for msg in rec.messages_json:
                    extracted.append(rec._extract_attachments(msg))
                rec.messages_json = extracted
        return records

    def action_start(self):
        self.ensure_one()
        if self.state not in ("draft", "paused"):
            return
        self.state = "running"
        return self._execute()

    def action_step(self):
        self.ensure_one()
        if self.state not in ("draft", "paused", "pending_tool_approval"):
            return
        self.state = "running"
        return self._execute_step()

    def action_resume(self):
        self.ensure_one()
        if self.state not in ("draft", "paused", "pending_tool_approval"):
            return
        self.state = "running"
        self.stepwise = False
        return self._execute()

    def _execute(self):
        while self.state == "running":
            self._execute_step()
            if self.stepwise and self.state == "paused":
                break

    def _execute_step(self):  # noqa: C901
        import logging

        _logger = logging.getLogger(__name__)

        self.ensure_one()
        if self.current_iteration >= self.max_iterations:
            self.state = "failed"
            self.error_message = "Max iterations reached."
            return

        self.current_iteration += 1
        connection = self.connection_id
        tools = self.tool_ids
        record = (
            self.env[self.res_model].browse(self.res_id)
            if self.res_model and self.res_id
            else None
        )

        # Rehydrate attachments if needed before sending to LLM
        messages = self._rehydrate_messages(list(self.messages_json or []))

        try:
            stream = self.stream
            stream_batch_size = self.stream_batch_size

            initial_messages = list(self.messages_json or [])

            accumulated_content, tool_calls, usage = connection._execute_ai_call(
                messages, tools, stream, stream_batch_size, self
            )

            response_message = {"role": "assistant", "content": accumulated_content}
            if tool_calls:
                response_message["tool_calls"] = tool_calls

            messages_json = list(self.messages_json or [])
            messages_json.append(response_message)

            p_tok = usage.get("prompt_tokens", 0)
            c_tok = usage.get("completion_tokens", 0)
            self.prompt_tokens += p_tok
            self.completion_tokens += c_tok

            tool_results = []
            pending_approval = False

            if tool_calls:
                tool_results, pending_approval = connection._process_tool_calls(
                    tool_calls, tools, record, execution_record=self
                )
                messages_json.extend(tool_results)

            if self.debug:
                self.env["ai.connection.execution.iteration"].create(
                    {
                        "execution_id": self.id,
                        "step_number": self.current_iteration,
                        "request_messages_json": initial_messages,
                        "response_message_json": response_message,
                        "tool_calls_json": tool_calls,
                        "tool_results_json": tool_results,
                    }
                )

            self.messages_json = messages_json

            if pending_approval:
                self.state = "pending_tool_approval"
            elif not tool_calls:
                self.state = "done"
                self.result_content = accumulated_content
            else:
                self.state = "paused" if self.stepwise else "running"

        except Exception as e:
            self.state = "failed"
            self.error_message = str(e)
            _logger.exception("AI Execution failed")

    def _should_execute_tool(self, tool, tool_call):
        return True

    def _on_stream_batch(self, accumulated_text, is_done=False):
        pass

    def _extract_attachments(self, message):
        import base64

        if not message.get("files"):
            return message
        new_files = []
        for file_data in message["files"]:
            if "content" in file_data and "attachment_id" not in file_data:
                # Ensure we handle bytes vs strings properly
                content = file_data["content"]
                if isinstance(content, str):
                    content = content.encode("utf-8")
                datas = base64.b64encode(content)
                att = self.env["ir.attachment"].create(
                    {
                        "name": file_data.get("name", "file"),
                        "datas": datas,
                        "res_model": self._name,
                        "res_id": self.id,
                    }
                )
                new_files.append(
                    {
                        "name": file_data.get("name"),
                        "mimetype": file_data.get("mimetype"),
                        "attachment_id": att.id,
                    }
                )
            else:
                new_files.append(file_data)
        message["files"] = new_files
        return message

    def _rehydrate_messages(self, messages):
        import base64

        res = []
        for msg in messages:
            if not msg.get("files"):
                res.append(msg)
                continue
            new_msg = dict(msg)
            new_files = []
            for file_data in new_msg["files"]:
                if "attachment_id" in file_data:
                    att = self.env["ir.attachment"].browse(file_data["attachment_id"])
                    if att.exists():
                        new_files.append(
                            {
                                "name": file_data.get("name", att.name),
                                "mimetype": file_data.get("mimetype", att.mimetype),
                                "content": base64.b64decode(att.datas).decode("utf-8"),
                            }
                        )
                else:
                    new_files.append(file_data)
            new_msg["files"] = new_files
            res.append(new_msg)
        return res
