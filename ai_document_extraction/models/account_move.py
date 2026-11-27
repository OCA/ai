# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import io
import json
import logging
import os
import re

from pdf2image import convert_from_bytes
from PIL import Image
from rapidfuzz import fuzz

from odoo import fields, models
from odoo.exceptions import UserError

from ..services import llm_extractor

_logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = ("pdf", "png", "jpg", "jpeg", "gif", "bmp")


class AccountMove(models.Model):
    _inherit = "account.move"

    ai_extraction_state = fields.Selection(
        [
            ("draft", "Not processed"),
            ("processing", "Processing"),
            ("done", "Done"),
            ("error", "Error"),
        ],
        string="AI Extraction State",
        default="draft",
        copy=False,
    )
    ai_raw_extraction = fields.Text(
        string="AI Raw Extraction",
        copy=False,
        readonly=True,
    )
    ai_extracted_tax = fields.Float(
        string="Extracted Tax Amount",
        copy=False,
        readonly=True,
    )
    ai_extracted_total = fields.Float(
        string="Extracted Total Amount",
        copy=False,
        readonly=True,
    )

    def _ai_connection(self, raise_if_missing=True):
        self.ensure_one()
        connection = (
            self.journal_id.ai_connection_id or self.company_id.ai_connection_id
        )
        if not connection.exists():
            if raise_if_missing:
                raise UserError(
                    self.env._(
                        "No AI Connection is configured for document extraction. "
                        "Configure one on the journal or in Accounting Settings."
                    )
                )
            return self.env["ai.connection"]
        return connection.sudo()

    def _ai_to_float(self, value):
        """Coerce an extracted amount to float, or None if not numeric."""
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.replace(",", ".").strip())
            except ValueError:
                return None
        return None

    def _ai_get_attachment(self):
        self.ensure_one()
        attachments = self.env["ir.attachment"].search(
            [
                ("res_model", "=", "account.move"),
                ("res_id", "=", self.id),
            ],
            order="create_date desc, id desc",
        )
        for attachment in attachments:
            if attachment.mimetype and attachment.mimetype.split("/")[-1] in (
                _IMAGE_EXTENSIONS
            ):
                return attachment
            if self._ai_file_extension(attachment.name) in _IMAGE_EXTENSIONS:
                return attachment
        return None

    def _ai_file_extension(self, filename):
        """Return the lower-cased file extension of ``filename``."""
        name = re.sub(r"\s+\(\d+\)$", "", filename or "")
        return name.rsplit(".", 1)[-1].lower()

    def _ai_is_processable(self, filename):
        """Whether the uploaded file can be handled by the AI extraction."""
        return self._ai_file_extension(filename) in _IMAGE_EXTENSIONS

    def _ai_find_processable_attachment(self, files_data):
        for file_data in files_data:
            if not self._ai_is_processable(file_data.get("name")):
                continue
            attachment = file_data.get("attachment")
            if attachment:
                return attachment
        return self._ai_get_attachment()

    def _extend_with_attachments(self, files_data, new=False):
        if not files_data:
            return False
        result = super()._extend_with_attachments(files_data, new=new)
        if result:
            return result
        if not all(
            self._ai_is_processable(file_data.get("name")) for file_data in files_data
        ):
            return result
        connection = self._ai_connection(raise_if_missing=False)
        attachment = self._ai_find_processable_attachment(files_data)
        if connection and attachment:
            self._extract_with_ai(attachment, connection=connection)
            return True
        self.message_post(
            body=self.env._(
                "The uploaded file is ready for AI extraction. "
                "Use 'Extract with AI' to fill the invoice."
            )
        )
        return True

    def action_extract_with_ai(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(
                self.env._("AI extraction is only available on draft moves.")
            )
        if self.move_type not in (
            "in_invoice",
            "in_receipt",
            "out_invoice",
            "out_receipt",
        ):
            raise UserError(self.env._("AI extraction is only available on invoices."))
        attachment = self._ai_get_attachment()
        if not attachment:
            raise UserError(
                self.env._("Attach the invoice PDF or image to the chatter first.")
            )
        connection = self._ai_connection(raise_if_missing=True)
        self._extract_with_ai(attachment, connection=connection)
        return True

    def action_review_extraction(self):
        self.ensure_one()
        partner_name = None
        if self.ai_raw_extraction:
            try:
                data = json.loads(self.ai_raw_extraction)
                partner_name = data.get("partner_name")
            except (ValueError, TypeError):
                _logger.debug(
                    "Could not parse stored AI extraction for move %s",
                    self.id,
                    exc_info=True,
                )
        wizard = self.env["extraction.wizard"].create(
            {
                "move_id": self.id,
                "extracted_partner_name": partner_name or "",
                "partner_id": self.partner_id.id,
            }
        )
        return {
            "name": self.env._("Review AI Extraction"),
            "type": "ir.actions.act_window",
            "res_model": "extraction.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def _ai_resize_image_bytes(self, image, max_dimension=1280):
        """Convert PIL image to RGB, cap dimensions, and return PNG bytes."""
        rgb_image = image.convert("RGB")
        width, height = rgb_image.size
        if max(width, height) > max_dimension:
            ratio = max_dimension / max(width, height)
            rgb_image = rgb_image.resize(
                (
                    max(1, round(width * ratio)),
                    max(1, round(height * ratio)),
                )
            )
        buffer = io.BytesIO()
        rgb_image.save(buffer, format="PNG")
        return buffer.getvalue()

    def _ai_prepare_attachments(self, attachment):
        """Render all PDF pages or image into resized PNG ir.attachment records."""
        self.ensure_one()
        data = attachment.with_context(bin_size=False).raw
        if not data:
            raise UserError(self.env._("The attachment is empty."))
        extension = self._ai_file_extension(attachment.name)
        if extension == "pdf" or (attachment.mimetype and "pdf" in attachment.mimetype):
            images = convert_from_bytes(data, dpi=200)
            if not images:
                raise UserError(self.env._("The PDF could not be rendered."))
        else:
            with Image.open(io.BytesIO(data)) as image:
                images = [image.copy()]
        base_name = os.path.splitext(attachment.name or "document")[0]
        prepared = self.env["ir.attachment"]
        for index, page_image in enumerate(images, start=1):
            png_bytes = self._ai_resize_image_bytes(page_image)
            prepared |= self.env["ir.attachment"].new(
                {
                    "name": f"{base_name}_page_{index}.png",
                    "datas": base64.b64encode(png_bytes),
                    "mimetype": "image/png",
                }
            )
        return prepared

    def _ai_extract_data(self, connection, prepared_attachments):
        """Run the vision LLM and parse the result, retrying once on failure."""
        prompt = llm_extractor._build_user_prompt(
            self._ai_available_taxes(), self._ai_available_currencies()
        )
        last_error = None
        for _attempt in range(2):
            try:
                content = connection._run(
                    prompt=prompt,
                    system_prompt=llm_extractor.SYSTEM_PROMPT,
                    record=self,
                    attachments=prepared_attachments,
                )[0]
                return llm_extractor.parse_and_validate(
                    content,
                    available_taxes=self._ai_available_taxes(),
                    available_currencies=self._ai_available_currencies(),
                )
            except ValueError as error:
                last_error = error
        raise last_error

    def _match_partner(self, name, threshold):
        if not name:
            return None
        partners = self.env["res.partner"].search(
            [
                ("is_company", "=", True),
                "|",
                ("company_id", "=", False),
                ("company_id", "=", self.company_id.id),
            ],
            limit=1000,
        )
        best, best_score = None, 0
        for partner in partners:
            score = fuzz.token_sort_ratio(name, partner.name or "")
            if score > best_score:
                best, best_score = partner, score
        if best and best_score >= threshold:
            return best
        return None

    def _ai_get_line_account(self):
        self.ensure_one()
        group = (
            "income"
            if self.move_type in ("out_invoice", "out_receipt", "out_refund")
            else "expense"
        )
        account = self.env["account.account"].search(
            [
                ("internal_group", "=", group),
                ("company_ids", "in", self.company_id.id),
            ],
            limit=1,
        )
        if not account:
            account = self.env["account.account"].search(
                [("company_ids", "in", self.company_id.id)], limit=1
            )
        return account

    def _ai_available_taxes(self):
        """Taxes the LLM may assign to invoice lines, keyed for the prompt."""
        self.ensure_one()
        use = (
            "sale"
            if self.move_type in ("out_invoice", "out_receipt", "out_refund")
            else "purchase"
        )
        taxes = self.env["account.tax"].search(
            [
                ("type_tax_use", "=", use),
                ("amount_type", "!=", "group"),
                ("amount", ">=", 0.0),
                ("active", "=", True),
                "|",
                ("company_id", "=", self.company_id.id),
                ("company_id", "=", False),
            ]
        )
        return [
            {
                "id": tax.id,
                "name": tax.name,
                "amount": tax.amount,
                "amount_type": tax.amount_type,
            }
            for tax in taxes
        ]

    def _ai_available_currencies(self):
        return self.env["res.currency"].search([("active", "=", True)]).mapped("name")

    def _ai_resolve_tax(self, tax_id=None, tax_rate=None):
        """Resolve an LLM tax reference to an account.tax record."""
        self.ensure_one()
        available = self._ai_available_taxes()
        if tax_id:
            try:
                tax_id = int(tax_id)
            except (ValueError, TypeError):
                tax_id = None
            for tax in available:
                if tax["id"] == tax_id:
                    return self.env["account.tax"].browse(tax_id)
        if tax_rate:
            try:
                rate = float(tax_rate)
            except (ValueError, TypeError):
                return self.env["account.tax"]
            for tax in available:
                if tax["amount_type"] == "percent" and abs(tax["amount"] - rate) < 1e-9:
                    return self.env["account.tax"].browse(tax["id"])
        return self.env["account.tax"]

    def _ai_set_lines(self, lines, description=None):
        self.ensure_one()
        account = self._ai_get_line_account()
        commands = [(2, line.id) for line in self.line_ids]
        for line in lines:
            name = (line.get("name") or description or "").strip()
            quantity = self._ai_to_float(line.get("quantity"))
            price_unit = self._ai_to_float(line.get("price_unit"))
            if quantity is None and price_unit is None:
                continue
            tax = self._ai_resolve_tax(line.get("tax_id"), line.get("tax_rate"))
            commands.append(
                (
                    0,
                    0,
                    {
                        "name": name,
                        "account_id": account.id,
                        "quantity": quantity if quantity else 1.0,
                        "price_unit": price_unit if price_unit else 0.0,
                        "tax_ids": [(6, 0, tax.ids)] if tax else [],
                    },
                )
            )
        self.line_ids = commands

    def _apply_extraction(self, data):
        self.ensure_one()
        values = {}
        invoice_date = data.get("invoice_date")
        if invoice_date:
            try:
                values["invoice_date"] = fields.Date.to_date(invoice_date)
            except ValueError:
                _logger.debug(
                    "Invalid invoice_date extracted for move %s: %s",
                    self.id,
                    invoice_date,
                )
        else:
            self.message_post(
                body=self.env._(
                    "The invoice date could not be extracted; "
                    "please review the draft before posting."
                )
            )
        invoice_number = data.get("invoice_number")
        payment_reference = data.get("payment_reference")
        if invoice_number:
            values["ref"] = invoice_number
        elif payment_reference:
            values["ref"] = payment_reference
            self.message_post(
                body=self.env._(
                    "No invoice/receipt number found; payment reference was used."
                )
            )
        if payment_reference:
            values["payment_reference"] = payment_reference
        partner = None
        threshold = self.company_id.ai_fuzzy_match_threshold or 85
        if data.get("partner_name"):
            partner = self._match_partner(data["partner_name"], threshold)
            if partner:
                values["partner_id"] = partner.id
        currency_code = data.get("currency")
        if currency_code:
            currency = self.env["res.currency"].search(
                [("name", "=", str(currency_code).strip().upper())], limit=1
            )
            if currency and currency != self.company_id.currency_id:
                values["currency_id"] = currency.id
        if values:
            self.write(values)
        lines = data.get("lines") or []
        description = data.get("description")
        if lines:
            self._ai_set_lines(lines, description=description)
        else:
            untaxed = self._ai_to_float(data.get("amount_untaxed"))
            if untaxed and untaxed > 0:
                self._ai_set_lines([{"name": description or "", "price_unit": untaxed}])
        self.ai_extracted_tax = self._ai_to_float(data.get("amount_tax")) or 0.0
        self.ai_extracted_total = self._ai_to_float(data.get("amount_total")) or 0.0
        return partner

    def _extract_with_ai(self, attachment, connection=None):
        self.ensure_one()
        self.ai_extraction_state = "processing"
        try:
            connection = connection or self._ai_connection(raise_if_missing=True)
            prepared = self._ai_prepare_attachments(attachment)
            data = self._ai_extract_data(connection, prepared)
            self._apply_extraction(data)
            self.ai_raw_extraction = json.dumps(data, indent=2)
            self.ai_extraction_state = "done"
            self.message_post(body=self.env._("AI extraction completed."))
        except Exception as error:  # noqa: BLE001
            self.ai_extraction_state = "error"
            _logger.warning(
                "AI extraction failed for move %s: %s", self.id, error, exc_info=True
            )
            self.message_post(body=self.env._("AI extraction failed: %s", error))
