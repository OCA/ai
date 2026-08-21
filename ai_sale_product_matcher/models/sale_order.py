# Copyright 2026 VSL
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging

from odoo import fields, models
from odoo.exceptions import UserError

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

    def action_open_ai_requirement_wizard(self):
        self.ensure_one()
        wizard = self.env["ai.sale.requirement.wizard"].create(
            {
                "order_id": self.id,
                "requirement_text": self.ai_requirement_raw_text or "",
                "requirements_json": self.ai_requirement_json or "",
                "ai_connection_id": self.ai_connection_id.id
                or self._ai_default_connection().id,
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

    def _ai_default_connection(self):
        param = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("ai_sale_product_matcher.ai_connection_id", "0")
        )
        try:
            cid = int(param or 0)
        except ValueError:
            cid = 0
        conn = self.env["ai.connection"].browse(cid)
        if conn.exists():
            return conn
        # Fallback to any openai_compatible connection
        return self.env["ai.connection"].search([("active", "=", True)], limit=1)

    def _ai_prepare_image(self, attachment):
        from ..services.image_preprocessor import prepare_image

        return prepare_image(attachment)

    def _ai_cleanup_tmp(self, path):
        from ..services.image_preprocessor import cleanup_tmp

        cleanup_tmp(path)

    def action_extract_requirements(self, attachment_ids=None, requirement_text=None):
        """Queue extraction job (called from wizard)."""
        self.ensure_one()
        if attachment_ids is None:
            attachment_ids = []
        # Resolve attachments
        attachments = self.env["ir.attachment"].browse(attachment_ids).exists()
        # Pick connection
        connection = self.ai_connection_id or self._ai_default_connection()
        if not connection or not connection.exists():
            raise UserError(
                self.env._(
                    "No AI Connection configured. Set one in the wizard or Settings."
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
        self.with_delay()._extract_requirements_job(
            attachment_ids=attachments.ids,
            requirement_text=requirement_text or "",
            connection_id=connection.id,
        )
        return True

    def _extract_requirements_job(
        self, attachment_ids, requirement_text, connection_id
    ):
        self.ensure_one()
        connection = self.env["ai.connection"].browse(connection_id).sudo()
        tmp_paths = []
        try:
            from ..services import requirement_extractor

            messages = []
            # If we have images/pdfs, prepare them
            attachments = self.env["ir.attachment"].browse(attachment_ids)
            for att in attachments:
                try:
                    img_path = self._ai_prepare_image(att)
                    tmp_paths.append(img_path)
                    messages.append(
                        requirement_extractor.build_vision_message(
                            img_path, connection, requirement_text=requirement_text
                        )
                    )
                except Exception as e:
                    _logger.warning("AI prepare image failed for %s: %s", att.name, e)

            if not messages:
                # Text-only
                if not (requirement_text or "").strip():
                    raise UserError(
                        self.env._("Provide a document or requirement text.")
                    )
                messages = [requirement_extractor.build_text_message(requirement_text)]

            # For multiple images, send each as separate message loop (model will get all)
            # We combine: system + each vision message, then final text message if needed
            # Actually ai_connection._run expects messages list; we send system + user messages
            # We'll run once per image and merge, simplest: run first image + text
            if len(messages) > 1:
                # Merge into one user message with multiple images - send sequentially
                # For Ollama/OpenAI, we can send multiple user messages; combine into one call
                # Use first message's image plus text; for others, append as additional user messages
                pass

            # Run LLM
            content = None
            last_error = None
            for _attempt in range(2):
                try:
                    # Build messages for client: system + user(s)
                    all_messages = []
                    # System is injected by connection._run via system_prompt
                    for msg in messages:
                        all_messages.append(msg)
                    content = connection._run(
                        system_prompt=requirement_extractor.SYSTEM_PROMPT,
                        messages=all_messages,
                    )[0]
                    break
                except Exception as e:
                    last_error = e
                    _logger.warning("AI requirement extraction attempt failed: %s", e)
            if content is None:
                raise last_error or ValueError("AI extraction failed")

            data = requirement_extractor.parse_and_validate(content)
            # Store
            self.write(
                {
                    "ai_requirement_json": json.dumps(
                        data, ensure_ascii=False, indent=2
                    ),
                    "ai_requirement_state": "done",
                    "ai_requirement_error": False,
                }
            )
            # Notify bus
            self.env["bus.bus"]._sendone(
                self.env.user.partner_id,
                "ai_sale_product_matcher.requirement_done",
                {"order_id": self.id, "state": "done"},
            )
            # Auto-run matching
            self._ai_run_matching()
        except Exception as e:
            _logger.exception("AI requirement extraction failed for order %s", self.id)
            self.write(
                {
                    "ai_requirement_state": "error",
                    "ai_requirement_error": str(e)[:2000],
                }
            )
            self.env["bus.bus"]._sendone(
                self.env.user.partner_id,
                "ai_sale_product_matcher.requirement_done",
                {"order_id": self.id, "state": "error", "error": str(e)[:500]},
            )
        finally:
            for p in tmp_paths:
                self._ai_cleanup_tmp(p)

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
        # Clear old matches
        self.ai_match_ids.unlink()
        # Find products - consider only storable/saleable templates with PIM attrs?
        # Use product.template search
        domain = [("sale_ok", "=", True)]
        # Optional: filter by PIM? include all
        products = self.env["product.template"].search(domain, limit=500)
        from ..services.product_matcher import find_best_matches

        best = find_best_matches(requirements, products, limit=10)
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

    def action_add_matched_products(self):
        """Add selected matches as order lines (called from wizard or matches view)."""
        self.ensure_one()
        # This is handled per-match via ai.product.match action; keep for bulk
        return True

    # ai_tool registration for MCP
    def _ai_find_products(self, requirements=None, record=None, **kwargs):
        """Generic AI tool: find products matching requirements dict."""
        if requirements is None:
            requirements = kwargs
        if not isinstance(requirements, dict):
            raise ValueError("requirements must be a dict")
        from ..services.product_matcher import find_best_matches

        products = self.env["product.template"].search(
            [("sale_ok", "=", True)], limit=200
        )
        best = find_best_matches(requirements, products, limit=10)
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
