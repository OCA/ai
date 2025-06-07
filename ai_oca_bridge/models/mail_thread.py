# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from lxml import etree

from odoo import api, fields, models
from odoo.tools.misc import frozendict


class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    ai_bridge_info = fields.Json(compute="_compute_ai_bridge_info", store=False)

    @api.depends()
    def _compute_ai_bridge_info(self):
        for record in self:
            record.ai_bridge_info = [
                bridge._get_info() for bridge in record._get_ai_bridge_info()
            ]

    def _get_ai_bridge_info(self):
        self.ensure_one()
        model_id = self.env["ir.model"].sudo().search([("model", "=", self._name)]).id
        return (
            self.env["ai.bridge"]
            .search([("model_id", "=", model_id), ("usage", "=", "thread")])
            .filtered(lambda r: r._enabled_for(self))
        )

    @api.model
    def get_view(self, view_id=None, view_type="form", **options):
        res = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type == "form":
            View = self.env["ir.ui.view"]
            if view_id and res.get("base_model", self._name) != self._name:
                View = View.with_context(base_model_name=res["base_model"])
            doc = etree.XML(res["arch"])

            # We need to copy, because it is a frozen dict
            all_models = res["models"].copy()
            for node in doc.xpath("/form/div[hasclass('oe_chatter')]"):
                # _add_tier_validation_label process
                new_node = etree.fromstring(
                    "<field name='ai_bridge_info' invisible='1'/>"
                )
                new_arch, new_models = View.postprocess_and_fields(new_node, self._name)
                new_node = etree.fromstring(new_arch)
                for model in list(filter(lambda x: x not in all_models, new_models)):
                    if model not in res["models"]:
                        all_models[model] = new_models[model]
                    else:
                        all_models[model] = res["models"][model]
                node.addprevious(new_node)
            res["arch"] = etree.tostring(doc)
            res["models"] = frozendict(all_models)
        return res

    @api.model
    def _get_view_fields(self, view_type, models):
        """
        We need to add this in order to fix the usage of form opening from
        trees inside a form
        """
        result = super()._get_view_fields(view_type, models)
        if view_type == "form":
            result[self._name].add("ai_bridge_info")
        return result
