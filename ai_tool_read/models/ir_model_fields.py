# Copyright 2026 Quartile (https://www.quartile.co)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class IrModelFields(models.Model):
    _inherit = "ir.model.fields"

    ai_no_read = fields.Boolean(
        string="AI Read Forbidden",
        default=False,
        index=True,
        help="If enabled, the generic AI read tools leave this field out of the "
        "records they return and of the fields described by get_fields. It does not "
        "stop an agent from filtering or sorting on the field (see the module's Known "
        "issues). Use it to keep personal or otherwise sensitive values out of the "
        "results given to AI agents.",
    )

    def write(self, vals):
        # ``ai_no_read`` is an add-on flag with no schema/ORM side effects, so it
        # must stay settable even on base (non-manual) fields -- which is the
        # whole point (e.g. flagging res.partner.email). Core write() forbids
        # altering base fields, so route just this key through the plain ORM
        # write and let everything else keep the standard validation. Copy the
        # dict first: popping the key must not be visible to the caller, which
        # may reuse the same ``vals`` for another write.
        vals = dict(vals)
        if "ai_no_read" in vals:
            flag_value = vals.pop("ai_no_read")
            models.Model.write(self, {"ai_no_read": flag_value})
        if vals:
            return super().write(vals)
        return True
