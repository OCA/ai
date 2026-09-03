# Copyright 2026-TODAY Akretion - Raphael Valyi <raphael.valyi@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import html as html_module
import logging
import re

from markupsafe import Markup

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class HermesWebhook(http.Controller):
    """Endpoint for Hermes gateway to post responses back to Odoo."""

    @http.route("/hermes/notify/<string:token>", type="json", auth="public", csrf=False)
    def hermes_notify(self, token, **kwargs):
        """Send a web notification to an Odoo user.

        This endpoint uses the web_notify module (soft dependency) to display
        toast notifications in the user's browser. If web_notify is not
        installed, it falls back to posting a message in the user's DM channel.

        Expected JSON body:
        {
            "user_id": 2,
            "message": "Production order blocked!",
            "title": "Alert",
            "type": "danger",  # success, warning, info, danger, default
            "sticky": true,
            "action": {        # optional: open a record on click
                "type": "ir.actions.act_window",
                "res_model": "mrp.production",
                "res_id": 123,
                "views": [[False, "form"]]
            }
        }
        """
        # Validate token
        gateway = (
            request.env["hermes.gateway"]
            .sudo()
            .search([("webhook_token", "=", token), ("active", "=", True)], limit=1)
        )
        if not gateway:
            return {"status": "error", "message": "Invalid token"}, 403

        data = request.get_json_data()
        if not data:
            return {"status": "error", "message": "No JSON data"}, 400

        user_id = data.get("user_id")
        if not user_id:
            return {"status": "error", "message": "Missing user_id"}, 400

        user = request.env["res.users"].sudo().browse(int(user_id))
        if not user.exists():
            return {"status": "error", "message": "User not found"}, 404

        # Build notification parameters
        notif_message = data.get("message", "")
        notif_title = data.get("title", "Hermes")
        notif_type = data.get("type", "info")
        sticky = data.get("sticky", False)
        action = data.get("action")

        # Try web_notify first (soft dependency)
        notify_method = getattr(user, f"notify_{notif_type}", None)
        if notify_method:
            try:
                notify_method(
                    notif_message,
                    title=notif_title,
                    sticky=sticky,
                    action=action,
                )
                return {
                    "status": "ok",
                    "method": "web_notify",
                    "user_id": user.id,
                }
            except Exception as e:
                _logger.warning("web_notify failed, falling back to DM: %s", e)

        # Fallback: post to user's DM channel
        return self._notify_fallback(gateway, user, notif_title, notif_message)

    def _notify_fallback(self, gateway, user, title, message):
        """Fallback notification via DM when web_notify is not available."""
        try:
            channel = (
                request.env["discuss.channel"]
                .with_user(gateway.ai_user_id.id)
                .sudo()
                .channel_get(partner_ids=[user.partner_id.id])
            )
            posted = channel.message_post(
                body=f"<p><b>{title}</b></p><p>{message}</p>",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
            return {
                "status": "ok",
                "method": "dm_fallback",
                "message_id": posted.id,
                "channel_id": channel.id,
            }
        except Exception as e:
            _logger.error("Fallback notification failed: %s", e)
            return {"status": "error", "message": str(e)}, 500

    @http.route("/hermes/push/<string:token>", type="json", auth="public", csrf=False)
    def hermes_push(self, token, **kwargs):
        """Push a proactive message from Hermes to a channel.

        Unlike the webhook endpoint (which is a response to a queued message),
        this endpoint allows Hermes to initiate a conversation or send
        notifications without a prior user message.

        Expected JSON body:
        {
            "channel_id": 42,
            "body": "Alert: production order blocked!",
            "action": "post_message"  # or "typing"
        }
        """
        # Validate token
        gateway = (
            request.env["hermes.gateway"]
            .sudo()
            .search([("webhook_token", "=", token), ("active", "=", True)], limit=1)
        )
        if not gateway:
            return {"status": "error", "message": "Invalid token"}, 403

        data = request.get_json_data()
        if not data:
            return {"status": "error", "message": "No JSON data"}, 400

        channel_id = data.get("channel_id")
        if not channel_id:
            return {"status": "error", "message": "Missing channel_id"}, 400

        # Dispatch to action handler (same as webhook)
        action = data.get("action", "post_message")
        if action == "post_message":
            return self._action_post_message(gateway, channel_id, data)
        elif action == "typing":
            return self._action_typing(
                gateway, channel_id, data.get("is_typing", False)
            )
        else:
            return {"status": "error", "message": f"Unknown action: {action}"}, 400

    @http.route(
        "/hermes/webhook/<string:token>", type="json", auth="public", csrf=False
    )
    def hermes_webhook(self, token, **kwargs):
        """Receive a response from Hermes and post it to the channel.

        Expected JSON body:
        {
            "channel_id": 42,
            "body": "Hello from Hermes!",
            "session_key": "odoo:abc123:channel_42",
            "action": "post_message"  # or "typing", "escalate"
        }
        """
        # Validate token
        gateway = (
            request.env["hermes.gateway"]
            .sudo()
            .search([("webhook_token", "=", token), ("active", "=", True)], limit=1)
        )
        if not gateway:
            return {"status": "error", "message": "Invalid token"}, 403

        data = request.get_json_data()
        if not data:
            return {"status": "error", "message": "No JSON data"}, 400

        channel_id = data.get("channel_id")
        if not channel_id:
            return {"status": "error", "message": "Missing channel_id"}, 400

        # Dispatch to action handler
        action = data.get("action", "post_message")
        if action == "post_message":
            return self._action_post_message(gateway, channel_id, data)
        elif action == "typing":
            return self._action_typing(
                gateway, channel_id, data.get("is_typing", False)
            )
        elif action == "escalate":
            return self._action_escalate(gateway, channel_id, data)
        else:
            return {"status": "error", "message": f"Unknown action: {action}"}, 400

    def _action_post_message(self, gateway, channel_id, data):
        """Post a message response to the channel."""
        body = data.get("body", "")
        if not body:
            return {"status": "error", "message": "Missing body"}, 400

        channel = request.env["discuss.channel"].sudo().browse(channel_id)
        if not channel.exists():
            return {"status": "error", "message": "Channel not found"}, 404

        # Get the AI user from the gateway
        ai_user = gateway.ai_user_id
        if not ai_user:
            return {"status": "error", "message": "No AI user configured"}, 500

        # Convert plain text to HTML if needed
        body_html = self._format_body(body)

        # Post the message as the AI user
        try:
            message = (
                channel.with_user(ai_user.id)
                .with_context(
                    mail_create_nosubscribe=True,
                    mail_notrack=True,
                )
                .message_post(
                    body=Markup(body_html),  # Mark as safe HTML
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment",
                )
            )

            # Mark any processing messages for this channel as done
            try:
                with request.env.cr.savepoint():
                    queue = (
                        request.env["hermes.message.queue"]
                        .sudo()
                        .search(
                            [
                                ("channel_id", "=", channel.id),
                                ("state", "=", "processing"),
                            ]
                        )
                    )
                    if queue:
                        queue.write({"state": "done"})
            except Exception:
                # Ignore concurrent update errors on queue cleanup
                _logger.debug("Concurrent update ignored during queue cleanup")

            return {
                "status": "ok",
                "message_id": message.id,
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}, 500

    def _action_typing(self, gateway, channel_id, is_typing):
        """Show/hide typing indicator."""
        channel = request.env["discuss.channel"].sudo().browse(channel_id)
        if not channel.exists():
            return {"status": "error", "message": "Channel not found"}, 404
        for member in channel.channel_member_ids:
            if member.partner_id == gateway.ai_user_id.partner_id:
                member._notify_typing(is_typing=is_typing)
        return {"status": "ok"}

    def _action_escalate(self, gateway, channel_id, data):
        """Handle escalation to human support.

        EXTENSION POINT: Override in a child module to implement escalation
        (e.g., create a helpdesk.ticket, notify a support team, etc.).
        """
        return {
            "status": "ok",
            "message": "Escalation not implemented in base module. "
            "Override _action_escalate() in a child module.",
        }

    def _format_body(self, body):
        """Format Hermes plain text response as Odoo HTML.

        Hermes returns plain text with markdown-like formatting.
        We convert it to simple HTML for Odoo's Discuss.
        """
        if not body:
            return "<p></p>"

        # Strip HTML tags from input to get plain text
        # (Odoo messages already come as HTML, we want the text content)
        text = re.sub(r"<[^>]+>", "", body)
        text = html_module.unescape(text)  # Decode HTML entities

        if not text.strip():
            return "<p></p>"

        # Escape HTML entities
        text = html_module.escape(text)

        # Convert URLs to links
        url_pattern = re.compile(r"(https?://[^\s<>\"{}|\\^`\[\]]+)")
        text = url_pattern.sub(r'<a href="\1" target="_blank">\1</a>', text)

        # Odoo Discuss wraps messages in <span>, so we use that
        return f"<span>{text}</span>"
