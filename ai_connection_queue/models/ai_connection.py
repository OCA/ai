# Copyright 2026 SDi
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models

ASYNC_CONTEXT_KEY = "ai_connection_async"
NOTIFY_MODEL_CONTEXT_KEY = "ai_connection_notify_model"
NOTIFY_RES_ID_CONTEXT_KEY = "ai_connection_notify_res_id"
NOTIFY_METHOD_CONTEXT_KEY = "ai_connection_notify_method"
RUN_CONTEXT_KEY = "ai_connection_run_id"


class AiConnection(models.Model):
    _inherit = "ai.connection"

    def _job_prepare_context_before_enqueue_keys(self):
        return super()._job_prepare_context_before_enqueue_keys() + (RUN_CONTEXT_KEY,)

    def _run_ai_step(
        self,
        messages,
        tools,
        record,
        max_iterations,
        iteration,
        prompt_tokens,
        completion_tokens,
    ):
        if iteration == 0 and RUN_CONTEXT_KEY not in self.env.context:
            if self.env.context.get(ASYNC_CONTEXT_KEY):
                run = self._create_async_run(messages, tools, record, max_iterations)
                self._dispatch_round(
                    run,
                    messages=messages,
                    tools=tools,
                    record=record,
                    max_iterations=max_iterations,
                    iteration=iteration,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
                return run.id

        return super()._run_ai_step(
            messages=messages,
            tools=tools,
            record=record,
            max_iterations=max_iterations,
            iteration=iteration,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def _create_async_run(self, messages, tools, record, max_iterations):
        self.ensure_one()
        notify_model = self.env.context.get(NOTIFY_MODEL_CONTEXT_KEY)
        notify_res_id = self.env.context.get(NOTIFY_RES_ID_CONTEXT_KEY)
        notify_method = self.env.context.get(NOTIFY_METHOD_CONTEXT_KEY)
        if bool(notify_model) != bool(notify_method):
            raise ValueError(
                f"{NOTIFY_MODEL_CONTEXT_KEY} and {NOTIFY_METHOD_CONTEXT_KEY} "
                "must be given together."
            )
        return self.env["ai.connection.run"].create(
            {
                "connection_id": self.id,
                "messages": list(messages),
                "tool_ids": [(6, 0, tools.ids)] if tools else False,
                "res_model": record._name if record else False,
                "res_id": record.id if record else False,
                "max_iterations": max_iterations or self._max_iterations,
                "notify_res_model": notify_model or False,
                "notify_res_id": notify_res_id or False,
                "notify_method": notify_method or False,
            }
        )

    def _dispatch_round(self, run, **kwargs):
        """Queue one round for `run`, tagging it with `run`'s id via context
        so it (and everything it recurses into) can find its way back to it.

        A distinct `identity_key` per round matters here: without it, a
        retried or duplicated dispatch for the same round could run twice in
        parallel and corrupt `run`'s state (two rounds both reading
        iteration N and writing iteration N+1 independently).
        """
        self.with_context(**{RUN_CONTEXT_KEY: run.id}).with_delay(
            identity_key=f"ai-connection-run-{run.id}-{kwargs['iteration']}"
        )._run_ai_step(**kwargs)

    def _run_ai_next(
        self,
        messages,
        tools,
        record,
        max_iterations,
        iteration,
        prompt_tokens,
        completion_tokens,
    ):
        run_id = self.env.context.get(RUN_CONTEXT_KEY)
        if not run_id:
            return super()._run_ai_next(
                messages=messages,
                tools=tools,
                record=record,
                max_iterations=max_iterations,
                iteration=iteration,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        run = self.env["ai.connection.run"].browse(run_id)
        run.write(
            {
                "messages": messages,
                "iteration": iteration,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            }
        )
        run._notify_progress()
        self._dispatch_round(
            run,
            messages=messages,
            tools=tools,
            record=record,
            max_iterations=max_iterations,
            iteration=iteration,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        return None

    def _run_ai_finalize(self, messages, prompt_tokens, completion_tokens, iteration):
        run_id = self.env.context.get(RUN_CONTEXT_KEY)
        if not run_id:
            return super()._run_ai_finalize(
                messages, prompt_tokens, completion_tokens, iteration
            )

        run = self.env["ai.connection.run"].browse(run_id)
        run.write(
            {
                "state": "done",
                "result": messages[-1]["content"],
                "messages": messages,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "iteration": iteration,
            }
        )
        run._notify_progress()
        return None

    def _run_ai_error(self, message):
        run_id = self.env.context.get(RUN_CONTEXT_KEY)
        if not run_id:
            return super()._run_ai_error(message)

        run = self.env["ai.connection.run"].browse(run_id)
        run.write({"state": "error", "error_message": message})
        run._notify_progress()
        return None
