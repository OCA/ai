# Copyright 2025 Dixmit
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo import fields, http
from odoo.http import request
from odoo.tools import consteq
from odoo.tools.translate import _


class AIController(http.Controller):
    @http.route(
        [
            "/ai/response/<int:execution_id>/<string:token>",
        ],
        type="http",
        auth="public",
        cors="*",
        csrf=False,
    )
    def ai_process_response(self, execution_id, token):
        execution = request.env["ai.bridge.execution"].sudo().browse(execution_id)
        if not execution.exists():
            return request.make_response(_("Execution not found."), status=404)
        if not consteq(execution._generate_token(), token):
            return request.make_response(
                _("Token is not allowed for this execution."), status=404
            )
        if (
            not execution.expiration_date
            or execution.expiration_date < fields.Datetime.now()
        ):
            return request.make_response(_("Execution is expired."), status=404)
        return request.make_response(
            json.dumps(
                execution._process_response(
                    json.loads(
                        request.httprequest.get_data().decode(
                            request.httprequest.charset
                        )
                    )
                )
            ),
            headers=[
                ("Content-Type", "application/json"),
            ],
        )
