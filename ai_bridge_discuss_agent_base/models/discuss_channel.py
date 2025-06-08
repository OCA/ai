import json
import logging
import random
import time

import requests
from markdown import markdown
from markupsafe import Markup

from odoo import _, api, models

from odoo.addons.queue_job.delay import Delayable, DelayableChain

_logger = logging.getLogger(__name__)

MARKDOWN_EXTENSIONS = [
    "markdown.extensions.fenced_code",
    "markdown.extensions.codehilite",
    "markdown.extensions.tables",
    "markdown.extensions.sane_lists",
    "markdown.extensions.smarty",
    "markdown.extensions.nl2br",
    "markdown.extensions.extra",
]


class Channel(models.Model):
    _inherit = "discuss.channel"

    @api.returns("mail.message", lambda value: value.id)
    def message_post(self, *, message_type="notification", **kwargs):
        message = super(
            Channel,
            self.with_context(mail_create_nosubscribe=True, mail_post_autofollow=False),
        ).message_post(message_type=message_type, **kwargs)

        if self.env.context.get("agent_message"):
            return message

        message_author_id = message.author_id.id if message.author_id else None
        message_body = message.body
        message_recipient_ids = message.partner_ids

        if not message_body:
            return message

        channel_recipient_ids = self.sudo().channel_member_ids.filtered(
            lambda m: m.partner_id.id != message_author_id
        )
        channel_recipient_partner_ids = channel_recipient_ids.mapped("partner_id.id")
        channel_recipient_agent_users = (
            self.env["res.users"]
            .sudo()
            .search([("partner_id", "in", channel_recipient_partner_ids)])
            .filtered(lambda m: m.is_ai_agent)
        )

        if (
            self._is_message_from_non_ai_user(message_author_id)
            and self._is_channel_eligible_for_ai_response()
        ):
            for agent in channel_recipient_agent_users:
                channel_member = (
                    self.env["discuss.channel.member"]
                    .sudo()
                    .search(
                        [
                            ("channel_id", "=", self.id),
                            ("partner_id", "=", agent.partner_id.id),
                        ],
                        limit=1,
                    )
                )
                if channel_member:
                    self._notify_typing_via_controller(False, channel_member.id)
                self.with_delay(max_retries=1).get_ai_agent_response_task(
                    message, agent, channel_member
                )
        elif self._has_recipient_ai_agent(
            message_recipient_ids, channel_recipient_agent_users
        ):
            channel_recipient_agent_users = channel_recipient_agent_users.filtered(
                lambda m: m.partner_id.id in message_recipient_ids.ids
            )
            for agent in channel_recipient_agent_users:
                channel_member = (
                    self.env["discuss.channel.member"]
                    .sudo()
                    .search(
                        [
                            ("channel_id", "=", self.id),
                            ("partner_id", "=", agent.partner_id.id),
                        ],
                        limit=1,
                    )
                )
                if channel_member:
                    self._notify_typing_via_controller(False, channel_member.id)
                self.with_delay(max_retries=1).get_ai_agent_response_task(
                    message, agent, channel_member
                )
        return message

    @api.model
    def get_ai_agent_response_task(self, message, recipient_agent, channel_member):
        try:
            start_time = time.time()
            method_name = f"{recipient_agent.api_type}_get_ai_agent_response_task"

            if hasattr(self, method_name):
                method = getattr(self, method_name)
                response, is_ai_agent_failed = method(
                    self.sudo().browse(self.id).id, message, recipient_agent
                )

                elapsed_time = time.time() - start_time
                fast_api_response = elapsed_time < recipient_agent.simulated_delay_min

                delayables = []
                for index, item in enumerate(response):
                    if not isinstance(item, dict):
                        item = {}

                    response_message_body = item.get(
                        recipient_agent.custom_api_response_key,
                        _(
                            "Communication with this AI Agent didn't work this "
                            "time, please ask your provider for more details."
                        ),
                    )

                    message_data = {
                        "body": response_message_body,
                        "message_type": "comment",
                        "subtype_xmlid": "mail.mt_comment",
                    }

                    delayable_task = Delayable(self.sudo()).post_message_async(
                        recipient_agent.id,
                        message_data,
                        is_delayed=(fast_api_response or index != 0),
                        is_ai_agent_failed=is_ai_agent_failed,
                    )
                    delayables.append(delayable_task)

                if delayables:
                    chain = DelayableChain(*delayables)
                    chain.delay()

            else:
                _logger.error(f"Method '{method_name}' is not implemented.")

        finally:
            if channel_member:
                self._notify_typing_via_controller(False, channel_member.id)

        self.env.context = self.env.context.copy()
        self.env.context.pop("agent_message", None)

    def post_message_async(
        self,
        recipient_agent_id,
        message_data,
        is_delayed=False,
        is_ai_agent_failed=False,
    ):
        message_data["body"] = self._format_response_message(message_data["body"])
        recipient_agent = self.env["res.users"].sudo().browse(recipient_agent_id)

        channel_member = (
            self.env["discuss.channel.member"]
            .sudo()
            .search(
                [
                    ("channel_id", "=", self.id),
                    ("partner_id", "=", recipient_agent.partner_id.id),
                ],
                limit=1,
            )
        )

        if channel_member:
            self._notify_typing_via_controller(True, channel_member.id)

        try:
            if is_delayed and recipient_agent.simulated_delay:
                delay = random.uniform(
                    recipient_agent.simulated_delay_min,
                    recipient_agent.simulated_delay_max,
                )
                time.sleep(delay)
            message = (
                self.sudo()
                .with_user(recipient_agent)
                .with_context(agent_message=True)
                .message_post(**message_data)
            )
            if message and is_ai_agent_failed:
                message.sudo().write({"is_ai_agent_failed": is_ai_agent_failed})

        finally:
            if channel_member:
                self._notify_typing_via_controller(False, channel_member.id)

    @api.model
    def custom_api_get_ai_agent_response_task(
        self, channel_id, message, recipient_agent
    ):
        sender_user_id = message.author_id.id
        sender_partner = self.env["res.partner"].sudo().browse(sender_user_id)
        extra_data = {"channel_id": channel_id, "message_id": message.id}
        for api_parameter in recipient_agent.api_configuration_id.api_parameter_ids:
            if api_parameter.parameter_type == "sender":
                extra_data[api_parameter.name] = api_parameter.evaluate_parameter(
                    obj=sender_partner
                )
            elif api_parameter.parameter_type == "receiver":
                extra_data[api_parameter.name] = api_parameter.evaluate_parameter(
                    obj=recipient_agent.partner_id
                )
            elif api_parameter.parameter_type == "general":
                extra_data[api_parameter.name] = api_parameter.evaluate_parameter(
                    obj=self.sudo()
                )
        auth_token = (
            recipient_agent.header_auth_token
            if recipient_agent.auth_type == "token"
            else None
        )
        response, is_ai_agent_failed = self.custom_api_get_agent_response(
            recipient_agent.api_endpoint,
            recipient_agent.custom_api_method,
            message=message.body,
            extra_data=extra_data,
            timeout=recipient_agent.api_timeout,
            auth_token=auth_token,
        )
        return response, is_ai_agent_failed

    @api.model
    def custom_api_get_agent_response(
        self, endpoint, method, message, extra_data=None, timeout=30, auth_token=None
    ):
        header = {"Authorization": f"Bearer {auth_token}"} if auth_token else None
        is_ai_agent_failed = False
        if not all([endpoint, message]):
            _logger.error("At least one parameter has not been set (endpoint, message)")
            return [False], True

        request_data = {"message": message, "extra_data": extra_data}
        try:
            if method == "post":
                response = requests.post(
                    endpoint, json=request_data, timeout=timeout, headers=header
                )
            elif method == "get":
                response = requests.get(
                    endpoint, params=request_data, timeout=timeout, headers=header
                )
            if response.status_code == 200:
                response.raise_for_status()
                json_response = response.json()
                return json_response, False
            else:
                _logger.error(
                    f"Connection error, status code {str(response.status_code)}"
                )
                is_ai_agent_failed = True
        except requests.exceptions.RequestException as e:
            _logger.error(f"Connection has failed due to {str(e)}")
            is_ai_agent_failed = True
        except json.JSONDecodeError as e:
            _logger.error(f"Error decoding JSON due to {str(e)}")
            is_ai_agent_failed = True

        return [False], is_ai_agent_failed

    def _is_message_from_non_ai_user(self, message_author_id):
        is_not_ai_agent = (
            message_author_id
            not in self.env["res.partner"].sudo().get_ai_agent_partners().ids
            and not self.env["res.users"]
            .sudo()
            .search([("partner_id", "=", message_author_id)], limit=1)
            .is_ai_agent
        )
        is_not_root_partner = message_author_id != self.env.ref("base.partner_root").id
        return is_not_ai_agent and is_not_root_partner

    def _is_channel_eligible_for_ai_response(self):
        channel_member_count = len(self.sudo().channel_member_ids)
        is_private_channel = channel_member_count <= 2
        is_livechat_active = (
            self.sudo().livechat_channel_id and self.sudo().livechat_active
        )
        is_not_livechat = not self.sudo().livechat_channel_id
        return is_private_channel and (is_livechat_active or is_not_livechat)

    def _has_recipient_ai_agent(
        self, message_recipient_ids, channel_recipient_agent_users
    ):
        return any(
            user.partner_id.id in message_recipient_ids.ids
            for user in channel_recipient_agent_users
        )

    def _notify_typing_via_controller(self, is_typing, channel_member_id):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        endpoint = f"{base_url}/web/discuss/notify_typing"
        headers = {
            "Content-Type": "application/json",
        }
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "is_typing": is_typing,
                "channel_member_id": channel_member_id,
            },
        }
        try:
            response = requests.post(endpoint, json=payload, headers=headers, timeout=5)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            _logger.error(f"Failed to notify typing via controller: {e}")

    @api.model
    def _format_response_message(self, content):
        return Markup(markdown(content, extensions=MARKDOWN_EXTENSIONS))
