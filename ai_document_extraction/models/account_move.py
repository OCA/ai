# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
import os
import re
import tempfile

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services import llm_extractor

_logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = ("pdf", "png", "jpg", "jpeg", "gif", "bmp")


class AccountMove(models.Model):
    _inherit = "account.move"

    invoice_date = fields.Date(
        string="Invoice/Bill Date",
        index=True,
        copy=False,
        default=lambda self: fields.Date.context_today(self),
    )

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

    @api.model
    def _ai_get_param(self, param_name, default=None):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(f"ai_document_extraction.{param_name}", default=default)
        )

    def _ai_settings(self):
        self.ensure_one()
        try:
            num_ctx = int(self._ai_get_param("num_ctx", "8192"))
        except (TypeError, ValueError):
            num_ctx = None
        return {
            "api_base_url": self._ai_get_param(
                "api_base_url", "https://openrouter.ai/api/v1"
            ),
            "api_key": self._ai_get_param("api_key", ""),
            "model_name": self._ai_get_param(
                "model_name", "qwen/qwen3-vl-32b-instruct"
            ),
            "num_ctx": num_ctx,
            "keep_alive": self._ai_get_param("keep_alive", "30m"),
            "llm_timeout": int(self._ai_get_param("llm_timeout", "300")),
            "fuzzy_match_threshold": int(
                self._ai_get_param("fuzzy_match_threshold", "85")
            ),
        }

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
            order="create_date desc",
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
        """Return the lower-cased file extension of ``filename``.

        Odoo renames duplicate attachments with a " (N)" suffix (e.g.
        "invoice.pdf (1)"), so it is stripped before reading the extension.
        """
        name = re.sub(r"\s+\(\d+\)$", "", filename or "")
        return name.rsplit(".", 1)[-1].lower()

    def _ai_is_processable(self, filename):
        """Whether the uploaded file can be handled by the AI extraction."""
        return self._ai_file_extension(filename) in _IMAGE_EXTENSIONS

    def _extend_with_attachments(self, files_data, new=False):
        """Don't show the generic import error for files handled by the AI.

        Odoo posts "There was an error while importing the bill..." whenever no
        EDI decoder applies to an uploaded file. Images and PDFs have no EDI
        decoder but are perfectly valid for our AI extraction, so treat them as
        successfully imported and guide the user to the AI button instead.
        """
        result = super()._extend_with_attachments(files_data, new=new)
        if (
            not result
            and files_data
            and all(
                self._ai_is_processable(file_data.get("name"))
                for file_data in files_data
            )
        ):
            self.message_post(
                body=self.env._(
                    "The uploaded file is ready for AI extraction. "
                    "Use 'Extract with AI' to fill the invoice."
                )
            )
            return True
        return result

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
        self.ai_extraction_state = "processing"
        self.message_post(body=self.env._("AI extraction started."))
        self.with_delay()._extract_with_ai_job(attachment.id)
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

    def _ai_resize_image(self, path, max_dimension=1280):
        """Cap the image size to keep vision-model tokens and latency low."""
        from PIL import Image

        with Image.open(path) as image:
            image = image.convert("RGB")
            width, height = image.size
            if max(width, height) <= max_dimension:
                return path
            ratio = max_dimension / max(width, height)
            image = image.resize(
                (
                    max(1, round(width * ratio)),
                    max(1, round(height * ratio)),
                )
            )
            resized = f"{path}.resized.png"
            image.save(resized, "PNG")
        os.unlink(path)
        return resized

    def _ai_prepare_image(self, attachment):
        data = attachment.with_context(bin_size=False).raw
        extension = self._ai_file_extension(attachment.name)
        handle, file_path = tempfile.mkstemp(suffix=f".{extension}")
        os.close(handle)
        try:
            with open(file_path, "wb") as file_handle:
                file_handle.write(data)
            if extension == "pdf":
                from pdf2image import convert_from_path

                images = convert_from_path(
                    file_path, dpi=200, first_page=1, last_page=1
                )
                if not images:
                    raise UserError(self.env._("The PDF could not be rendered."))
                png_path = f"{file_path}.png"
                images[0].save(png_path, "PNG")
                os.unlink(file_path)
                file_path = png_path
            return self._ai_resize_image(file_path)
        except Exception:
            self._ai_cleanup_tmp(file_path)
            raise

    def _ai_cleanup_tmp(self, path):
        for candidate in (path, f"{path}.png"):
            if os.path.exists(candidate):
                try:
                    os.unlink(candidate)
                except OSError:
                    _logger.debug("Could not remove temporary file %s", candidate)

    def _ai_store_processed_image(self, processed_path):
        """Store the OCR-ready image as an attachment on the move."""
        self.ensure_one()
        if not processed_path or not os.path.exists(processed_path):
            return
        import base64

        with open(processed_path, "rb") as image_file:
            datas = base64.b64encode(image_file.read())
        self.env["ir.attachment"].create(
            {
                "name": f"{self.name or 'move'}-ai-processed.png",
                "datas": datas,
                "mimetype": "image/png",
                "res_model": "account.move",
                "res_id": self.id,
            }
        )

    def _match_partner(self, name, threshold):
        if not name:
            return None
        try:
            from rapidfuzz import fuzz
        except ImportError:  # pragma: no cover
            return None
        partners = self.env["res.partner"].search(
            [("is_company", "=", True)], limit=1000
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
        if self.move_type in ("out_invoice", "out_receipt", "out_refund"):
            account = self.env["account.account"].search(
                [
                    ("internal_group", "=", "income"),
                    ("company_ids", "in", self.company_id.id),
                ],
                limit=1,
            )
        else:
            account = self.env["account.account"].search(
                [
                    ("internal_group", "=", "expense"),
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
        """Resolve an LLM tax reference to an account.tax record.

        Exact match only: by tax id, or by tax rate against the available
        percent taxes. Unknown references yield an empty recordset so the
        line stays untaxed.
        """
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
        settings = self._ai_settings()
        if data.get("partner_name"):
            partner = self._match_partner(
                data["partner_name"], settings["fuzzy_match_threshold"]
            )
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

    def _extract_with_ai_job(self, attachment_id):
        self.ensure_one()
        attachment = self.env["ir.attachment"].browse(attachment_id)
        image_path = None
        try:
            image_path = self._ai_prepare_image(attachment)
            settings = self._ai_settings()
            data = llm_extractor.extract_invoice_data_from_image(
                image_path,
                settings["api_base_url"],
                settings["model_name"],
                settings["api_key"],
                available_taxes=self._ai_available_taxes(),
                available_currencies=self._ai_available_currencies(),
                num_ctx=settings["num_ctx"],
                keep_alive=settings["keep_alive"],
                timeout=settings["llm_timeout"],
            )
            self._ai_store_processed_image(image_path)
            self._apply_extraction(data)
            self.ai_raw_extraction = json.dumps(data, indent=2)
            self.ai_extraction_state = "done"
            self.message_post(body=self.env._("AI extraction completed."))
        except Exception as error:  # noqa: BLE001 - job boundary
            self.ai_extraction_state = "error"
            _logger.error(
                "AI extraction failed for move %s: %s", self.id, error, exc_info=True
            )
            self.message_post(body=self.env._("AI extraction failed: %s", error))
        finally:
            if image_path:
                self._ai_cleanup_tmp(image_path)
        self._ai_notify_state_change()

    def _ai_notify_state_change(self):
        """Notify the web client that the AI extraction state changed."""
        try:
            self.env["bus.bus"]._sendone(
                f"ai_document_extraction.move.{self.id}",
                "ai_document_extraction",
                {"move_id": self.id, "state": self.ai_extraction_state},
            )
        except Exception as error:  # noqa: BLE001 - notification must not break the job
            _logger.warning(
                "Could not notify AI extraction state change for move %s: %s",
                self.id,
                error,
                exc_info=True,
            )
