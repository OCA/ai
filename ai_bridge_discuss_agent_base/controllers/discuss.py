from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request


class DiscussAgentsController(http.Controller):
    @http.route("/web/discuss/notify_typing", type="json", auth="public", cors="*")
    def notify_typing(self, is_typing, channel_member_id):
        try:
            channel_member = (
                request.env["discuss.channel.member"].sudo().browse(channel_member_id)
            )

            if not channel_member or not channel_member.exists():
                raise NotFound()

            channel_member._notify_typing(is_typing=is_typing)

            return {"success": True}

        except NotFound:
            return {"success": False, "error": "Channel member not found"}
        except Exception:
            return {"success": False, "error": "Failed to send typing notification"}
