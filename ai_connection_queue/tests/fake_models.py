# Copyright 2026 SDi
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models

# A plain in-process list is enough here: tests drive every queued round
# synchronously through trap_jobs(), so this always runs in the same Python
# process as the assertions reading it - a real, cross-process run would
# have to observe this through the `ai.connection.run` record itself, not a
# module-level variable like this one.
notify_calls = []
notify_model_calls = []


class ResPartnerNotifyReceiver(models.Model):
    _inherit = "res.partner"

    def _ai_connection_run_test_callback(self, run):
        notify_calls.append((self.id, run.state, run.iteration))

    @api.model
    def _ai_connection_run_test_model_callback(self, run):
        # `self` is whatever recordset the callback was called on - a
        # model-level (notify_model) call resolves it as env[model], i.e.
        # empty, same as any other `@api.model` call.
        notify_model_calls.append((tuple(self.ids), run.state, run.iteration))
