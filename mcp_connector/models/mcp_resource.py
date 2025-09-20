# Copyright 2025 Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class McpResource(models.Model):
    _name = "mcp.resource"
    _description = "MCP Resource"
    _order = "server_id, name"

    name = fields.Char(string="Resource Name", required=True, index=True)
    server_id = fields.Many2one(
        "mcp.server", string="Server", required=True, ondelete="cascade", index=True
    )
    server_state = fields.Selection(
        related="server_id.state", string="Server Status", readonly=True
    )
    uri = fields.Char(
        string="URI",
        required=True,
        index=True,
        help="Uniform Resource Identifier for the resource",
    )
    mime_type = fields.Char(
        string="MIME Type",
        required=True,
        help="MIME type of the resource (e.g., application/json)",
    )
    description = fields.Text()
    is_template = fields.Boolean(
        default=False,
        help="Whether this is a resource template with URI parameters",
    )
    uri_template = fields.Char(
        string="URI Template",
        help="URI template with parameters (e.g., weather://{city}/current)",
    )
    template_parameters = fields.Text(
        help="JSON array of template parameter definitions",
        default="[]",
    )

    _sql_constraints = [
        (
            "server_uri_uniq",
            "unique(server_id, uri)",
            "Resource URI must be unique per server!",
        )
    ]

    @api.constrains("template_parameters")
    def _check_template_parameters(self):
        for record in self:
            if record.template_parameters:
                try:
                    params_json = json.loads(record.template_parameters)
                    if not isinstance(params_json, list):
                        raise ValidationError(
                            _("Template parameters must be a JSON array")
                        )
                except json.JSONDecodeError:
                    raise ValidationError(
                        _("Template parameters must be valid JSON")
                    ) from None

    def action_read_resource(self):
        """Open a wizard to read the resource."""
        self.ensure_one()

        if self.is_template:
            return {
                "name": _("Read Resource Template: %s") % self.name,
                "type": "ir.actions.act_window",
                "res_model": "mcp.resource.read.wizard",
                "view_mode": "form",
                "target": "new",
                "context": {
                    "default_resource_id": self.id,
                    "default_server_id": self.server_id.id,
                    "default_uri_template": self.uri_template or self.uri,
                    "default_is_template": True,
                },
            }
        else:
            return {
                "name": _("Read Resource: %s") % self.name,
                "type": "ir.actions.act_window",
                "res_model": "mcp.resource.read.wizard",
                "view_mode": "form",
                "target": "new",
                "context": {
                    "default_resource_id": self.id,
                    "default_server_id": self.server_id.id,
                    "default_uri": self.uri,
                    "default_is_template": False,
                },
            }

    async def _async_read_resource(self, uri):
        """Read a resource from the MCP server using async API.

        Args:
            uri: The URI of the resource to read

        Returns:
            The resource contents
        """

        # Parse command and arguments from the server
        command = self.server_id.command
        args = json.loads(self.server_id.args) if self.server_id.args else []
        env_vars = (
            json.loads(self.server_id.env_vars) if self.server_id.env_vars else None
        )

        # Log the command that will be executed
        _logger.info(
            "Reading resource %s from MCP server with command: %s %s",
            uri,
            command,
            " ".join(args),
        )

        # Create server parameters

        server_params = StdioServerParameters(command=command, args=args, env=env_vars)

        result = None

        # Connect to the server via stdio
        async with stdio_client(server_params) as (read, write):
            # Log successful connection
            _logger.info("Successfully established stdio connection to MCP server")

            async with ClientSession(read, write) as session:
                # Initialize the connection
                await session.initialize()
                _logger.info("Successfully initialized MCP session")

                # Read the resource
                _logger.info("Reading resource with URI: %s", uri)
                response = await session.read_resource(uri)

                # Process the response
                result = {"contents": []}

                # Extract content from the response
                for content_item in response.contents:
                    if hasattr(content_item, "text"):
                        result["contents"].append(
                            {
                                "uri": content_item.uri,
                                "mimeType": content_item.mimeType,
                                "text": content_item.text,
                            }
                        )
                    else:
                        # Handle binary content if needed
                        result["contents"].append(
                            {
                                "uri": content_item.uri,
                                "mimeType": content_item.mimeType,
                                "data": content_item.data,
                            }
                        )

                _logger.info("Successfully read resource %s", uri)

        return result

    def read_resource(self, uri=None, params=None):
        """Read the resource from the MCP server.

        Args:
            uri (str, optional): The URI to read. If not provided, the resource's URI will
            be used.
            params (dict, optional): Parameters to substitute in the URI template.

        Returns:
            dict: The resource contents
        """
        self.ensure_one()

        if self.server_id.state != "running":
            raise UserError(_("Server is not running"))

        # Determine the URI to use
        if uri is None:
            if self.is_template:
                if not params:
                    raise UserError(_("Parameters are required for resource templates"))

                # Implement URI template substitution
                uri = self.uri_template
                for key, value in params.items():
                    uri = uri.replace(f"{{{key}}}", value)
            else:
                uri = self.uri

        try:
            _logger.info("Reading resource %s from server %s", uri, self.server_id.name)

            # Check if MCP SDK is available
            if not hasattr(self.server_id, "_run_async_in_thread"):
                raise UserError(
                    _(
                        "MCP SDK is not available. Please install it with: pip install mcp"
                    )
                )

            # Use the server's async methods to communicate with the MCP server
            result = self.server_id._run_async_in_thread(self._async_read_resource(uri))

            return result
        except Exception as e:
            _logger.exception(
                "Error reading resource %s from server %s: %s",
                uri,
                self.server_id.name,
                str(e),
            )
            # Provide a more user-friendly error message
            error_message = str(e)
            if "EAI_AGAIN" in error_message or "getaddrinfo" in error_message:
                raise UserError(
                    _(
                        "Network connectivity issue: Unable to connect to MCP server. \
                            Please check your internet connection and proxy settings."
                    )
                ) from None
            elif "Method not found" in error_message:
                raise UserError(
                    _(
                        "The MCP server does not support the read_resource method. \
                            Please update the server implementation."
                    )
                ) from None
            else:
                raise UserError(
                    _("Failed to read resource: %s") % error_message
                ) from None
