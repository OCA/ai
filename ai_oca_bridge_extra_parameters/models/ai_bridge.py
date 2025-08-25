from odoo import fields, models


class AiBridge(models.Model):

    _inherit = "ai.bridge"

    extra_parameter_ids = fields.Many2many(
        "ai.extra.parameter",
        string="Extra Parameters",
        help="Additional parameters to be sent to the AI system. "
        "These can be used to customize the AI request using expressions or fixed input.",
    )

    def _prepare_payload(self, record=None, **kwargs):
        payload = super()._prepare_payload(record=record, **kwargs)
        if self.extra_parameter_ids:
            if (
                record is None
                and self.env.context.get("sample_payload")
                and self.model_id
            ):
                record = self.env[self.model_id.model].search([], limit=1)
                if not record:
                    return payload
            payload["extra_parameters"] = {}
            for param in self.extra_parameter_ids:
                context_obj = None
                if param.parameter_type == "record":
                    context_obj = record
                elif param.parameter_type == "self":
                    context_obj = self
                payload["extra_parameters"][param.name] = param.evaluate_parameter(
                    obj=context_obj
                )
        return payload
