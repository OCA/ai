# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging

from odoo import fields, models
from odoo.exceptions import UserError

from ..services import requirement_extractor
from ..services.image_preprocessor import (
    extract_text_from_pdf,
    is_processable,
    render_attachment_images,
)
from ..services.product_matcher import find_best_matches

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    ai_requirement_state = fields.Selection(
        [
            ("draft", "Not processed"),
            ("extracting", "Extracting"),
            ("done", "Done"),
            ("error", "Error"),
        ],
        string="AI Requirement State",
        default="draft",
        copy=False,
    )
    ai_requirement_json = fields.Text(
        string="Extracted Requirements (JSON)",
        copy=False,
    )
    ai_requirement_raw_text = fields.Text(
        string="Requirement Text",
        copy=False,
    )
    ai_requirement_error = fields.Text(
        string="AI Error",
        copy=False,
        readonly=True,
    )
    ai_connection_id = fields.Many2one(
        "ai.connection",
        string="AI Connection",
        copy=False,
    )
    ai_match_ids = fields.One2many(
        "ai.product.match",
        "order_id",
        string="AI Product Matches",
        copy=False,
    )
    ai_filter_categ_id = fields.Many2one(
        "product.category",
        string="AI Filter Category",
        help="Optional product category filter (including subcategories) "
        "for AI matching.",
        copy=False,
    )

    def _get_ai_connection(self):
        self.ensure_one()
        return self.ai_connection_id or self.company_id.ai_sale_matcher_connection_id

    def action_open_ai_requirement_wizard(self):
        self.ensure_one()
        connection = self._get_ai_connection()
        wizard = self.env["ai.sale.requirement.wizard"].create(
            {
                "order_id": self.id,
                "requirement_text": self.ai_requirement_raw_text or "",
                "requirements_json": self.ai_requirement_json or "",
                "ai_connection_id": connection.id if connection else False,
                "categ_id": self.ai_filter_categ_id.id or False,
                "state": "done" if self.ai_requirement_state == "done" else "draft",
            }
        )
        return {
            "name": self.env._("Find Products with AI"),
            "type": "ir.actions.act_window",
            "res_model": "ai.sale.requirement.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_extract_requirements(self, attachment_ids=None, requirement_text=None):
        """Extract structured customer requirements via the configured AI connection."""
        self.ensure_one()
        attachments = self.env["ir.attachment"].browse(attachment_ids or []).exists()
        connection = self._get_ai_connection()
        if not connection:
            raise UserError(
                self.env._(
                    "No AI Connection configured. Set one in the wizard or "
                    "Sales Settings."
                )
            )
        self.write(
            {
                "ai_requirement_state": "extracting",
                "ai_requirement_raw_text": requirement_text
                or self.ai_requirement_raw_text,
                "ai_connection_id": connection.id,
                "ai_requirement_error": False,
            }
        )
        rendered_attachments = self.env["ir.attachment"]
        try:
            extracted_texts = []
            for att in attachments:
                if not is_processable(att.name) and att.mimetype != "application/pdf":
                    continue
                try:
                    rendered_attachments |= render_attachment_images(self.env, att)
                    txt = extract_text_from_pdf(att)
                    if txt:
                        extracted_texts.append(txt[:4000])
                except Exception as err:
                    _logger.warning(
                        "AI image preparation failed for %s: %s", att.name, err
                    )
            combined_text = ""
            if extracted_texts:
                combined_text += "\n\nPDF extracted text:\n" + "\n---\n".join(
                    extracted_texts
                )
            if requirement_text and requirement_text.strip():
                combined_text += (
                    "\n\nUser requirement text:\n" + requirement_text.strip()
                )
            combined_text = combined_text.strip()
            if not rendered_attachments and not combined_text:
                raise UserError(self.env._("Provide a document or requirement text."))
            user_prompt = requirement_extractor._build_user_prompt(
                requirement_text=combined_text,
                env=self.env,
            )
            data = None
            last_error = None
            for _attempt in range(2):
                try:
                    content = connection._run(
                        prompt=user_prompt,
                        system_prompt=requirement_extractor.SYSTEM_PROMPT,
                        record=self,
                        attachments=rendered_attachments or None,
                    )[0]
                    data = requirement_extractor.parse_and_validate(
                        content, env=self.env
                    )
                    break
                except Exception as err:
                    last_error = err
                    _logger.warning("AI requirement extraction attempt failed: %s", err)
            if data is None:
                raise last_error or ValueError("AI extraction failed")
            self.write(
                {
                    "ai_requirement_json": json.dumps(
                        data, ensure_ascii=False, indent=2
                    ),
                    "ai_requirement_state": "done",
                    "ai_requirement_error": False,
                }
            )
            self.ai_match_ids.unlink()
        except UserError:
            self.ai_requirement_state = "error"
            raise
        except Exception as err:
            _logger.warning(
                "AI requirement extraction failed for order %s: %s",
                self.id,
                err,
            )
            self.write(
                {
                    "ai_requirement_state": "error",
                    "ai_requirement_error": str(err)[:2000],
                }
            )
        finally:
            if rendered_attachments:
                rendered_attachments.unlink()
        return True

    def _ai_run_matching(self):
        self.ensure_one()
        if not self.ai_requirement_json:
            return
        try:
            requirements = json.loads(self.ai_requirement_json)
        except (ValueError, TypeError):
            return
        if not requirements:
            return
        self.ai_match_ids.unlink()
        domain = [("sale_ok", "=", True)]
        if self.ai_filter_categ_id:
            domain.append(("categ_id", "child_of", self.ai_filter_categ_id.id))
        products = self.env["product.template"].search(domain, limit=500)
        best = find_best_matches(requirements, products, limit=10, env=self.env)
        for prod, score in best:
            self.env["ai.product.match"].create(
                {
                    "order_id": self.id,
                    "product_tmpl_id": prod.id,
                    "product_id": prod.product_variant_id.id
                    if prod.product_variant_id
                    else False,
                    "match_count": score["match_count"],
                    "total_required": score["total"],
                    "match_percent": score["percent"],
                    "weighted_percent": score["weighted_percent"],
                    "matched_keys": json.dumps(
                        score["matched_keys"], ensure_ascii=False
                    ),
                    "mismatched_keys": json.dumps(
                        score["mismatched_keys"], ensure_ascii=False
                    ),
                    "missing_keys": json.dumps(
                        score["missing_keys"], ensure_ascii=False
                    ),
                }
            )

    def _ai_find_products(self, requirements=None, record=None, **kwargs):
        """AI tool callback: find products matching a requirements dict."""
        if requirements is None:
            requirements = kwargs
        if not isinstance(requirements, dict):
            raise ValueError("requirements must be a dict")
        products = self.env["product.template"].search(
            [("sale_ok", "=", True)], limit=200
        )
        best = find_best_matches(requirements, products, limit=10, env=self.env)
        return {
            "matches": [
                {
                    "product_id": prod.id,
                    "name": prod.display_name,
                    "match_count": score["match_count"],
                    "total": score["total"],
                    "percent": score["percent"],
                    "weighted_percent": score["weighted_percent"],
                }
                for prod, score in best
            ]
        }
