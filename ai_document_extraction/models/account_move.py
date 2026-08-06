# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
import os
import tempfile

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services import image_preprocessor, llm_extractor, ocr_engine

_logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = ("pdf", "png", "jpg", "jpeg", "gif", "bmp")
_DEFAULT_LINE_NAME = "AI extracted amount"


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

    @api.model
    def _ai_get_param(self, param_name, default=None):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(f"ai_document_extraction.{param_name}", default=default)
        )

    def _ai_settings(self):
        self.ensure_one()
        return {
            "api_base_url": self._ai_get_param(
                "api_base_url", "http://ollama:11434/v1"
            ),
            "api_key": self._ai_get_param("api_key", "dummy"),
            "model_name": self._ai_get_param("model_name", "qwen3:4b"),
            "ocr_language": self._ai_get_param("ocr_language", "tur+eng"),
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
            name = attachment.name or ""
            if attachment.mimetype and attachment.mimetype.split("/")[-1] in (
                _IMAGE_EXTENSIONS
            ):
                return attachment
            if name.rsplit(".", 1)[-1].lower() in _IMAGE_EXTENSIONS:
                return attachment
        return None

    def action_extract_with_ai(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(
                self.env._("AI extraction is only available on draft moves.")
            )
        if self.move_type not in ("in_invoice", "in_receipt"):
            raise UserError(
                self.env._("AI extraction is only available on vendor bills.")
            )
        attachment = self._ai_get_attachment()
        if not attachment:
            raise UserError(
                self.env._("Attach the invoice PDF or image to the chatter first.")
            )
        self.ai_extraction_state = "processing"
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

    def _ai_prepare_image(self, attachment):
        data = attachment.with_context(bin_size=False).raw
        extension = (attachment.name or "file").rsplit(".", 1)[-1].lower()
        handle, file_path = tempfile.mkstemp(suffix=f".{extension}")
        os.close(handle)
        try:
            with open(file_path, "wb") as file_handle:
                file_handle.write(data)
            if extension == "pdf":
                from pdf2image import convert_from_path

                images = convert_from_path(
                    file_path, dpi=300, first_page=1, last_page=1
                )
                if not images:
                    raise UserError(self.env._("The PDF could not be rendered."))
                png_path = f"{file_path}.png"
                images[0].save(png_path, "PNG")
                os.unlink(file_path)
                return png_path
            return file_path
        except Exception:
            os.unlink(file_path)
            raise

    def _ai_cleanup_tmp(self, path):
        for candidate in (path, f"{path}.png"):
            if os.path.exists(candidate):
                try:
                    os.unlink(candidate)
                except OSError:
                    _logger.debug("Could not remove temporary file %s", candidate)

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

    def _ai_set_untaxed_line(self, untaxed):
        self.ensure_one()
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
        stale = self.line_ids.filtered(lambda line: line.name == _DEFAULT_LINE_NAME)
        commands = [(2, line.id) for line in stale]
        commands.append(
            (
                0,
                0,
                {
                    "name": _DEFAULT_LINE_NAME,
                    "account_id": account.id,
                    "quantity": 1,
                    "price_unit": untaxed,
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
        if data.get("invoice_number"):
            values["ref"] = data["invoice_number"]
        partner = None
        settings = self._ai_settings()
        if data.get("partner_name"):
            partner = self._match_partner(
                data["partner_name"], settings["fuzzy_match_threshold"]
            )
            if partner:
                values["partner_id"] = partner.id
        if values:
            self.write(values)
        untaxed = self._ai_to_float(data.get("amount_untaxed"))
        if untaxed and untaxed > 0:
            self._ai_set_untaxed_line(untaxed)
        self.ai_extracted_tax = self._ai_to_float(data.get("amount_tax")) or 0.0
        self.ai_extracted_total = self._ai_to_float(data.get("amount_total")) or 0.0
        return partner

    def _extract_with_ai_job(self, attachment_id):
        self.ensure_one()
        attachment = self.env["ir.attachment"].browse(attachment_id)
        file_path = None
        processed_path = None
        try:
            file_path = self._ai_prepare_image(attachment)
            processed_path = image_preprocessor.preprocess_image(file_path)
            settings = self._ai_settings()
            ocr_text = ocr_engine.extract_text_with_layout(
                processed_path, settings["ocr_language"]
            )
            if not ocr_text.strip():
                raise UserError(self.env._("No text was detected in the document."))
            data = llm_extractor.extract_invoice_data(
                ocr_text,
                settings["api_base_url"],
                settings["model_name"],
                settings["api_key"],
            )
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
            if processed_path:
                self._ai_cleanup_tmp(processed_path)
            if file_path:
                self._ai_cleanup_tmp(file_path)
