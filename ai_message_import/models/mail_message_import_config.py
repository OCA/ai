# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..services.ai_client import AIClient
from ..services.prompts import PROMPT_PRODUCT_CHOICE


class MailMessageImportConfig(models.Model):
    """The settings of the AI that reads the conversations of the company."""

    _inherit = "mail.message.import.config"

    ai_connection_id = fields.Many2one(
        "ai.connection",
        string="AI connection",
        help="Connection of OCA/ai (provider, model and key) that reads the "
        "conversations of the company and chooses the products.",
    )
    freight_product_id = fields.Many2one(
        "product.product",
        string="Transport product",
        check_company=True,
        domain="[('type', '=', 'service')]",
        help="Service product used for the transport charges of the documents. "
        "Without it, the charges stay pending review.",
    )
    ai_product_choice = fields.Boolean(
        string="Products chosen by the AI",
        default=True,
        help="When no exact rule identifies the product of a line, the AI chooses "
        "it among the most similar products, the ones the partner takes first. "
        "The choice is noted on the order to be checked, and learned when the "
        "order is confirmed.",
    )
    ai_product_min_confidence = fields.Float(
        string="Minimum confidence of the choice", default=0.85, digits=(3, 2)
    )
    total_tolerance = fields.Float(
        string="Totals tolerance",
        default=0.05,
        digits=(16, 2),
        help="Difference allowed between the totals of a document and of its " "order.",
    )
    max_attachment_size_mb = fields.Integer(
        string="Maximum file size (MB)", default=20, required=True
    )
    max_batch_size_mb = fields.Integer(
        string="Maximum size per conversation (MB)", default=50, required=True
    )
    history_days = fields.Integer(
        string="Days of previous documents",
        default=60,
        required=True,
        help="Documents of the same sender sent to the AI to recognise " "corrections.",
    )
    ai_configured = fields.Boolean(
        string="AI configured", compute="_compute_ai_configured"
    )
    missing_prompts = fields.Char(
        compute="_compute_missing_prompts",
        help="AI prompts the installed modules need and nobody wrote yet.",
    )

    @api.constrains(
        "max_attachment_size_mb",
        "max_batch_size_mb",
        "history_days",
        "total_tolerance",
        "ai_product_min_confidence",
    )
    def _check_ai_values(self):
        for config in self:
            if not 0 <= config.ai_product_min_confidence <= 1:
                raise ValidationError(self.env._("The confidences go from 0 to 1."))
            if (
                min(config.max_attachment_size_mb, config.max_batch_size_mb) < 1
                or config.history_days < 0
                or config.total_tolerance < 0
            ):
                raise ValidationError(self.env._("The limits must be positive."))

    @api.depends("ai_connection_id")
    def _compute_ai_configured(self):
        for config in self:
            config.ai_configured = bool(config.ai_connection_id)

    @api.depends("ai_product_choice")
    def _compute_missing_prompts(self):
        missing = self.env["ai.message.import.prompt"]._missing_codes()
        for config in self:
            codes = [
                code
                for code in missing
                if config.ai_product_choice or code != PROMPT_PRODUCT_CHOICE
            ]
            config.missing_prompts = ", ".join(codes) or False

    def action_open_prompts(self):
        return self.env["ir.actions.act_window"]._for_xml_id(
            "ai_message_import.action_ai_message_import_prompt"
        )

    def _ai_client(self):
        """The client of the AI connection of the company.

        :raise AIError: when the company has no AI connection yet.
        """
        self.ensure_one()
        return AIClient(self.ai_connection_id)
