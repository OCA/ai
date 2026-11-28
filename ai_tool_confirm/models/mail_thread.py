# Copyright 2026 Coopdevs
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import api, models
from odoo.exceptions import AccessError
from odoo.models import LOG_ACCESS_COLUMNS, MAGIC_COLUMNS

from .ai_tool import executing_request

_logger = logging.getLogger(__name__)


class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    # Audit: a document created or modified by an approved AI action must say
    # so, and its request must list it. Only documents with a chatter: lines
    # and technical records would only add noise.

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        execution = executing_request.get()
        if execution:
            execution.created.update((rec._name, rec.id) for rec in records)
            execution.request._log_created_records(records)
        return records

    def write(self, vals):
        execution = executing_request.get()
        if execution:
            # Keep the value of each field before the first write of the
            # action, to know at the end what it really changed. No sudo:
            # read with the rights of this very write (whoever can write a
            # field can read it; a write as superuser reads as superuser).
            fnames = [f for f in vals if self._ai_tool_confirm_is_audited_field(f)]
            for rec in self:
                if not rec.id or (rec._name, rec.id) in execution.created:
                    continue
                initial = execution.initial_values.setdefault((rec._name, rec.id), {})
                for fname in fnames:
                    if fname in initial:
                        continue
                    try:
                        initial[fname] = rec[fname]
                    except AccessError:
                        # A rule letting write but not read: rare. The audit
                        # must never break the action: skip this field.
                        _logger.warning(
                            "AI tool request audit: cannot read %s.%s of %s",
                            rec._name,
                            fname,
                            rec,
                        )
        return super().write(vals)

    @api.model
    def _ai_tool_confirm_is_audited_field(self, fname):
        field = self._fields.get(fname)
        return bool(
            field
            and field.store
            and fname not in MAGIC_COLUMNS + LOG_ACCESS_COLUMNS
            # Chatter and activity bookkeeping, not business data
            and not fname.startswith(("message_", "activity_", "website_message"))
        )
