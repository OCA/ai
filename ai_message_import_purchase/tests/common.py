# Copyright 2026 Binhex
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import Command

from odoo.addons.ai_message_import.tests.common import AiMessageImportCase


class AiMessagePurchaseCase(AiMessageImportCase):
    """Vendor quotes, with vendors, products and prices."""

    DOCUMENT_TYPE = "purchase"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tax_21 = cls.env["account.tax"].create(
            {
                "name": "Purchase 21%",
                "amount": 21,
                "type_tax_use": "purchase",
                "company_id": cls.company.id,
            }
        )
        cls.vendor = cls.env["res.partner"].create(
            {
                "name": "Ferreteria Norte SL",
                "vat": "ESB12345674",
                "email": "ventas@ferreterianorte.example",
                "is_company": True,
                "supplier_rank": 1,
            }
        )
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        cls.uom_dozen = cls.env.ref("uom.product_uom_dozen")
        cls.uom_kg = cls.env.ref("uom.product_uom_kgm")
        cls.product_screw = cls._create_product("Screw M6", "SCR-M6", 0.5)
        cls.env["product.supplierinfo"].create(
            {
                "partner_id": cls.vendor.id,
                "product_tmpl_id": cls.product_screw.product_tmpl_id.id,
                "product_code": "FN-100",
                "price": 12.0,
                "min_qty": 1,
            }
        )
        cls.product_glue = cls._create_product("Glue 500ml", "GLU-500", 5.0)
        cls.product_free = cls._create_product("Sample brush", "BRU-01", 0.0)
        cls.product_box = cls._create_product("Nail 30mm", "NAI-30", 0.1)
        cls.packaging_box = cls.env["product.packaging"].create(
            {"name": "Caja 24", "product_id": cls.product_box.id, "qty": 24}
        )
        cls.freight = cls.env["product.product"].create(
            {
                "name": "Transport",
                "type": "service",
                "purchase_ok": True,
                "supplier_taxes_id": [Command.set(cls.tax_21.ids)],
            }
        )
        cls.config.freight_product_id = cls.freight

    @classmethod
    def _create_product(cls, name, code, cost, taxes=None):
        return cls.env["product.product"].create(
            {
                "name": name,
                "default_code": code,
                "standard_price": cost,
                "purchase_ok": True,
                "supplier_taxes_id": [
                    Command.set((taxes if taxes is not None else cls.tax_21).ids)
                ],
                **cls._product_type_values(),
            }
        )

    @classmethod
    def _product_type_values(cls):
        return {"type": "consu"}
