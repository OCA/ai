# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from lxml import etree

from odoo import api, fields, models
from odoo.tools.misc import frozendict


class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    ai_bridge_info = fields.Json(compute="_compute_ai_bridge_info")
    ai_form_btn_info = fields.Json(compute="_compute_ai_form_btn_info")
    ai_has_form_btn = fields.Boolean(compute="_compute_ai_form_btn_info")

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

    @api.depends()
    def _compute_ai_form_btn_info(self):
        for record in self:
            bridges = record._get_ai_form_btn_bridge_info()
            record.ai_form_btn_info = [
                bridge._get_form_btn_info() for bridge in bridges
            ]
            record.ai_has_form_btn = bool(bridges)

    def _get_ai_form_btn_bridge_info(self):
        self.ensure_one()
        model_id = self.env["ir.model"].sudo().search([("model", "=", self._name)]).id
        return (
            self.env["ai.bridge"]
            .search([("model_id", "=", model_id), ("usage", "=", "form_btn")])
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

            # Inject form buttons before <sheet> if form_btn bridges exist for this model
            sheet_nodes = doc.xpath("//sheet[not(ancestor::field)]")
            if sheet_nodes:
                model_id = self.env["ir.model"].sudo()._get_id(self._name)
                if model_id and self.env["ai.bridge"].sudo().search_count(
                    [
                        ("model_id", "=", model_id),
                        ("usage", "=", "form_btn"),
                        ("active", "=", True),
                    ]
                ):
                    str_element = self.env["ir.qweb"]._render(
                        "ai_oca_bridge.ai_form_btn_container", {}
                    )
                    new_arch, new_models = View.postprocess_and_fields(
                        etree.fromstring(str_element), self._name
                    )
                    for model, model_fields in new_models.items():
                        all_models[model] = tuple(
                            set(all_models.get(model, ())) | set(model_fields)
                        )
                    for node in sheet_nodes:
                        node.addprevious(etree.fromstring(new_arch))

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
            result[self._name].add("ai_form_btn_info")
            result[self._name].add("ai_has_form_btn")
        return result
