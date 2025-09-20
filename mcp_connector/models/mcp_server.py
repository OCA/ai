# Copyright 2025 Escodoo
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import asyncio
import json
import logging
import subprocess
import threading

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class McpServer(models.Model):
    _name = "mcp.server"
    _description = "MCP Server"
    _order = "name"

    name = fields.Char(string="Server Name", required=True, index=True)
    description = fields.Text()
    command = fields.Char(
        required=True,
        help="Command to run the MCP server (e.g., node, python)",
    )
    args = fields.Text(
        string="Arguments",
        required=True,
        help='Command arguments as a JSON array (e.g., ["/path/to/server.js"])',
    )
    env_vars = fields.Text(
        string="Environment Variables",
        help='Environment variables as a JSON object (e.g., {"API_KEY": "abc123"})',
    )
    active = fields.Boolean(default=True)
    enabled = fields.Boolean(
        default=False,
        help="Whether the server is enabled and will be started automatically",
    )
    auto_approve = fields.Text(
        help="List of tools that can be auto-approved as a JSON array "
        '(e.g., ["get_weather"])',
    )
    capabilities = fields.Text(
        help="Server capabilities as a JSON object",
        readonly=True,
    )
    state = fields.Selection(
        [
            ("stopped", "Stopped"),
            ("running", "Running"),
            ("error", "Error"),
        ],
        string="Status",
        default="stopped",
        readonly=True,
    )
    error_message = fields.Text(readonly=True)
    last_start_time = fields.Datetime(readonly=True)

    # Related fields
    tool_count = fields.Integer(compute="_compute_tool_count")
    resource_count = fields.Integer(compute="_compute_resource_count")
    prompt_count = fields.Integer(compute="_compute_prompt_count")

    _sql_constraints = [("name_uniq", "unique(name)", "Server name must be unique!")]

    @api.constrains("args", "env_vars", "auto_approve")
    def _check_json_fields(self):
        for record in self:
            # Validate args is a valid JSON array
            if record.args:
                try:
                    args_json = json.loads(record.args)
                    if not isinstance(args_json, list):
                        raise ValidationError(_("Arguments must be a JSON array"))
                except json.JSONDecodeError:
                    raise ValidationError(_("Arguments must be valid JSON")) from None

            # Validate env_vars is a valid JSON object
            if record.env_vars:
                try:
                    env_json = json.loads(record.env_vars)
                    if not isinstance(env_json, dict):
                        raise ValidationError(
                            _("Environment variables must be a JSON object")
                        )
                except json.JSONDecodeError:
                    raise ValidationError(
                        _("Environment variables must be valid JSON")
                    ) from None

            # Validate auto_approve is a valid JSON array
            if record.auto_approve:
                try:
                    auto_approve_json = json.loads(record.auto_approve)
                    if not isinstance(auto_approve_json, list):
                        raise ValidationError(_("Auto approve must be a JSON array"))
                except json.JSONDecodeError:
                    raise ValidationError(
                        _("Auto approve must be valid JSON")
                    ) from None

    def _compute_tool_count(self):
        for record in self:
            record.tool_count = self.env["mcp.tool"].search_count(
                [("server_id", "=", record.id)]
            )

    def _compute_resource_count(self):
        for record in self:
            record.resource_count = self.env["mcp.resource"].search_count(
                [("server_id", "=", record.id)]
            )

    def _compute_prompt_count(self):
        for record in self:
            record.prompt_count = self.env["mcp.prompt"].search_count(
                [("server_id", "=", record.id)]
            )

    def action_start(self):
        self.ensure_one()
        if self.state == "running":
            raise UserError(_("Server is already running"))

        try:
            # Parse command arguments and environment variables
            args_list = json.loads(self.args) if self.args else []
            env_dict = json.loads(self.env_vars) if self.env_vars else {}

            # Start server in a separate thread
            thread = threading.Thread(
                target=self._run_server, args=(self.command, args_list, env_dict)
            )
            thread.daemon = True
            thread.start()

            # Update server state
            self.write(
                {
                    "state": "running",
                    "error_message": False,
                    "last_start_time": fields.Datetime.now(),
                }
            )

            # Refresh tools and resources
            try:
                self._refresh_tools_and_resources()

                # Only show success notification if refresh completed without errors
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Server Started"),
                        "message": _('MCP server "%s" started successfully')
                        % self.name,
                        "sticky": False,
                        "type": "success",
                    },
                }

            except Exception as refresh_error:
                _logger.exception(
                    "Error refreshing tools and resources for server %s: %s",
                    self.name,
                    str(refresh_error),
                )
                # Update server state with the specific error
                self.write(
                    {
                        "state": "error",
                        "error_message": str(refresh_error),
                    }
                )

                # Show error notification instead of success
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Server Error"),
                        "message": _('MCP server "%(name)s" failed to start: %(error)s')
                        % {"name": self.name, "error": str(refresh_error)},
                        "sticky": True,
                        "type": "danger",
                    },
                }
        except Exception as e:
            self.write({"state": "error", "error_message": str(e)})
            raise UserError(_("Failed to start server: %s") % str(e)) from None

    def action_stop(self):
        self.ensure_one()
        if self.state != "running":
            raise UserError(_("Server is not running"))

        # TODO: Implement proper server stopping mechanism
        # For now, just update the state
        self.write({"state": "stopped", "error_message": False})

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Server Stopped"),
                "message": _('MCP server "%(name)s" stopped successfully')
                % {"name": self.name},
                "sticky": False,
                "type": "success",
            },
        }

    def action_view_tools(self):
        self.ensure_one()
        return {
            "name": _("Tools"),
            "type": "ir.actions.act_window",
            "res_model": "mcp.tool",
            "view_mode": "tree,form",
            "domain": [("server_id", "=", self.id)],
            "context": {"default_server_id": self.id},
        }

    def action_view_resources(self):
        self.ensure_one()
        return {
            "name": _("Resources"),
            "type": "ir.actions.act_window",
            "res_model": "mcp.resource",
            "view_mode": "tree,form",
            "domain": [("server_id", "=", self.id)],
            "context": {"default_server_id": self.id},
        }

    def action_view_prompts(self):
        self.ensure_one()
        return {
            "name": _("Prompts"),
            "type": "ir.actions.act_window",
            "res_model": "mcp.prompt",
            "view_mode": "tree,form",
            "domain": [("server_id", "=", self.id)],
            "context": {"default_server_id": self.id},
        }

    def action_call_tool(self, tool_name, arguments):
        """Call an MCP tool with the provided arguments.

        Args:
            tool_name: The name of the tool to call
            arguments: A dictionary of arguments to pass to the tool

        Returns:
            The result of the tool call
        """
        self.ensure_one()

        if self.state != "running":
            raise UserError(_("Cannot call tool: server %s is not running") % self.name)

        # Validate that the tool exists
        tool = self.env["mcp.tool"].search(
            [("server_id", "=", self.id), ("name", "=", tool_name)], limit=1
        )

        if not tool:
            raise UserError(
                _("Tool %(tool_name)s not found on server %(server_name)s")
                % {"tool_name": tool_name, "server_name": self.name}
            )

        try:
            # Run the async function in a synchronous context
            result = self._run_async_in_thread(
                self._async_call_tool(tool_name, arguments)
            )
            return result
        except Exception as e:
            _logger.exception(
                "Error calling tool %s on server %s: %s", tool_name, self.name, str(e)
            )
            # Provide a more user-friendly error message
            error_message = str(e)
            if "EAI_AGAIN" in error_message or "getaddrinfo" in error_message:
                raise UserError(
                    _(
                        "Network connectivity issue: Unable to connect to npm "
                        "registry. \
                            Please check your internet connection and proxy settings."
                    )
                ) from None
            elif "npm ERR!" in error_message:
                raise UserError(
                    _("NPM error: %s") % error_message.split("npm ERR!")[1].strip()
                ) from None
            else:
                raise UserError(_("Failed to call tool: %s") % error_message) from None

    def _run_server(self, command, args_list, env_dict):
        """Run the MCP server process."""
        try:
            # Prepare environment variables
            env = dict(subprocess.os.environ)
            env.update(env_dict)

            # Start the server process
            process = subprocess.Popen(
                [command] + args_list,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # TODO: Implement proper process management and communication
            # For now, just log the output
            for line in process.stdout:
                _logger.info("MCP Server %s: %s", self.name, line.strip())

            for line in process.stderr:
                _logger.error("MCP Server %s Error: %s", self.name, line.strip())

            # Wait for process to complete
            process.wait()

            # Update server state based on process exit code
            if process.returncode != 0:
                self.write(
                    {
                        "state": "error",
                        "error_message": f"Server exited with code "
                        f"{process.returncode}",
                    }
                )
            else:
                self.write({"state": "stopped"})

        except Exception as e:
            _logger.exception("Error running MCP server %s: %s", self.name, str(e))
            self.write({"state": "error", "error_message": str(e)})

    def _refresh_tools(self):
        """Refresh tools from the MCP server."""
        try:
            tools = self._get_tools_from_server()
            if tools:
                # Remove existing tools for this server
                self.env["mcp.tool"].search([("server_id", "=", self.id)]).unlink()

                # Create new tool records
                for tool in tools:
                    self.env["mcp.tool"].create(
                        {
                            "server_id": self.id,
                            "name": tool.get("name", ""),
                            "description": tool.get("description", ""),
                            "input_schema": json.dumps(tool.get("inputSchema", {})),
                            "output_schema": (
                                json.dumps(tool.get("outputSchema", {}))
                                if tool.get("outputSchema")
                                else None
                            ),
                        }
                    )
                _logger.info("Updated %d tools for server %s", len(tools), self.name)
        except Exception as tool_error:
            _logger.exception(
                "Error getting tools from server %s: %s", self.name, str(tool_error)
            )
            if self._handle_network_error(tool_error):
                return
            raise tool_error from None

    def _refresh_resources(self):
        """Refresh resources from the MCP server."""
        try:
            resources = self._get_resources_from_server()
            if resources:
                # Remove existing resources for this server
                self.env["mcp.resource"].search([("server_id", "=", self.id)]).unlink()

                # Create new resource records
                for resource in resources:
                    self.env["mcp.resource"].create(
                        {
                            "server_id": self.id,
                            "uri": resource.get("uri", ""),
                            "name": resource.get("name", ""),
                            "mime_type": resource.get(
                                "mimeType", ""
                            ),  # Keep snake_case for database field
                            "description": resource.get("description", ""),
                        }
                    )
                _logger.info(
                    "Updated %d resources for server %s", len(resources), self.name
                )
        except Exception as resource_error:
            _logger.exception(
                "Error getting resources from server %s: %s",
                self.name,
                str(resource_error),
            )
            if self._handle_network_error(resource_error):
                return
            raise resource_error from None

    def _refresh_prompts(self):
        """Refresh prompts from the MCP server."""
        try:
            prompts = self._get_prompts_from_server()
            if prompts:
                # Remove existing prompts for this server
                self.env["mcp.prompt"].search([("server_id", "=", self.id)]).unlink()

                # Create new prompt records
                for prompt in prompts:
                    self.env["mcp.prompt"].create(
                        {
                            "server_id": self.id,
                            "name": prompt.get("name", ""),
                            "description": prompt.get("description", ""),
                            "arguments": json.dumps(prompt.get("arguments", [])),
                        }
                    )
                _logger.info(
                    "Updated %d prompts for server %s", len(prompts), self.name
                )
        except Exception as prompt_error:
            _logger.exception(
                "Error getting prompts from server %s: %s",
                self.name,
                str(prompt_error),
            )
            if self._handle_network_error(prompt_error):
                return
            raise prompt_error from None

    def _handle_network_error(self, error):
        """Handle network-related errors."""
        if "EAI_AGAIN" in str(error) or "getaddrinfo" in str(error):
            self.write(
                {
                    "state": "error",
                    "error_message": _(
                        "Network connectivity issue: Unable to connect to MCP server. \
                            Please check your internet connection and proxy settings."
                    ),
                }
            )
            return True
        return False

    def _handle_refresh_error(self, error):
        """Handle general refresh errors."""
        error_message = str(error)
        if "EAI_AGAIN" in error_message or "getaddrinfo" in error_message:
            error_message = _(
                "Network connectivity issue: Unable to connect to MCP server. \
                    Please check your internet connection and proxy settings."
            )
        elif "npm ERR!" in error_message:
            error_message = (
                _("NPM error: %s") % error_message.split("npm ERR!")[1].strip()
            )
        else:
            error_message = (
                _("Failed to refresh tools and resources: %s") % error_message
            )

        self.write({"state": "error", "error_message": error_message})
        # Don't raise UserError here, let the calling method handle it
        return error_message

    async def _async_call_tool(self, tool_name, arguments):
        """Call an MCP tool with the provided arguments using async API.

        Args:
            tool_name: The name of the tool to call
            arguments: A dictionary of arguments to pass to the tool

        Returns:
            The result of the tool call
        """

        # Parse command and arguments
        command = self.command
        args = json.loads(self.args) if self.args else []
        env_vars = json.loads(self.env_vars) if self.env_vars else None

        # Log the command that will be executed
        _logger.info(
            "Calling tool %s on MCP server with command: %s %s",
            tool_name,
            command,
            " ".join(args),
        )

        # Create server parameters
        server_params = StdioServerParameters(command=command, args=args, env=env_vars)

        result = None

        try:
            # Connect to the server via stdio
            async with stdio_client(server_params) as (read, write):
                # Log successful connection
                _logger.info("Successfully established stdio connection to MCP server")

                try:
                    async with ClientSession(read, write) as session:
                        # Initialize the connection
                        await session.initialize()
                        _logger.info("Successfully initialized MCP session")

                        # Call the tool
                        _logger.info(
                            "Calling tool %s with arguments: %s", tool_name, arguments
                        )
                        response = await session.call_tool(tool_name, arguments)

                        # Process the response
                        result = {"content": [], "is_error": response.isError}

                        # Extract content from the response
                        for content_item in response.content:
                            if content_item.type == "text":
                                result["content"].append(
                                    {"type": "text", "text": content_item.text}
                                )
                            elif content_item.type == "image":
                                result["content"].append(
                                    {
                                        "type": "image",
                                        "data": content_item.data,
                                        "mime_type": content_item.mime_type,
                                    }
                                )

                        _logger.info("Successfully called tool %s", tool_name)

                except Exception as e:
                    _logger.exception("Error during MCP session: %s", str(e))
                    # Capture stderr output if available
                    if hasattr(read, "stderr") and read.stderr:
                        stderr_content = await read.stderr.read()
                        if stderr_content:
                            _logger.error(
                                "MCP server stderr: %s",
                                stderr_content.decode("utf-8", errors="replace"),
                            )
                    raise
        except Exception as e:
            _logger.exception("Error connecting to MCP server: %s", str(e))
            # Check if it's a network-related error
            if "EAI_AGAIN" in str(e) or "getaddrinfo" in str(e):
                raise UserError(
                    _(
                        "Network error connecting to MCP server. Please check your \
                            internet connection and proxy settings."
                    )
                ) from None
            raise

        return result

    def _test_mcp_command(self, command, args, env_vars):
        """Test MCP command and capture stderr for better error reporting."""
        stderr_message = ""
        try:
            import shutil

            # Find the correct command path
            command_path = shutil.which(command)
            if not command_path:
                _logger.warning("Command not found: %(command)s", {"command": command})
                return stderr_message

            # Test the command to capture stderr
            test_process = subprocess.Popen(
                [command_path] + args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env_vars,
                text=True,
            )

            # Wait a short time to see if there are immediate errors
            try:
                stdout, stderr = test_process.communicate(timeout=3)
                if stderr:
                    stderr_message = stderr.strip()
                    _logger.error(
                        "MCP server stderr during test: %(stderr)s",
                        {"stderr": stderr_message},
                    )
            except subprocess.TimeoutExpired:
                # If it doesn't timeout, that's good - kill the test process
                test_process.kill()
                test_process.wait()
        except Exception as test_error:
            _logger.warning(
                "Could not test MCP server command: %(error)s",
                {"error": str(test_error)},
            )
        return stderr_message

    def _is_configuration_error(self, error_message):
        """Check if error is related to configuration (missing env vars,
        API keys, etc.)."""
        return any(
            keyword in error_message.lower()
            for keyword in [
                "environment variable",
                "api key",
                "token",
                "not set",
                "missing",
            ]
        )

    async def _get_tools_from_session(self, session):
        """Get tools from MCP session."""
        _logger.info("Requesting tools from MCP server")
        tools_response = await session.list_tools()
        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema,
                "outputSchema": getattr(tool, "outputSchema", None),
            }
            for tool in tools_response.tools
        ]
        _logger.info("Received %(count)d tools from MCP server", {"count": len(tools)})
        return tools

    async def _get_resources_from_session(self, session):
        """Get resources from MCP session."""
        _logger.info("Requesting resources from MCP server")
        try:
            resources_response = await session.list_resources()
            resources = [
                {
                    "uri": resource.uri,
                    "name": resource.name,
                    "mimeType": resource.mimeType,
                    "description": resource.description,
                }
                for resource in resources_response.resources
            ]
            _logger.info(
                "Received %(count)d resources from MCP server",
                {"count": len(resources)},
            )
            return resources
        except Exception as resource_error:
            # Check if it's a "Method not found" error
            if "Method not found" in str(resource_error):
                _logger.warning(
                    "The MCP server does not support the list_resources "
                    "method. Skipping resources."
                )
                return []  # Return empty list of resources
            else:
                # Re-raise other errors
                raise

    async def _get_prompts_from_session(self, session):
        """Get prompts from MCP session."""
        _logger.info("Requesting prompts from MCP server")
        try:
            prompts_response = await session.list_prompts()
            prompts = [
                {
                    "name": prompt.name,
                    "description": prompt.description,
                    "arguments": prompt.arguments,
                }
                for prompt in prompts_response.prompts
            ]
            _logger.info(
                "Received %(count)d prompts from MCP server",
                {"count": len(prompts)},
            )
            return prompts
        except Exception as prompt_error:
            # Check if it's a "Method not found" error
            if "Method not found" in str(prompt_error):
                _logger.warning(
                    "The MCP server does not support the list_prompts "
                    "method. Skipping prompts."
                )
                return []  # Return empty list of prompts
            else:
                # Re-raise other errors
                raise

    async def _async_connect_and_query_mcp(self):
        """Connect to the MCP server and query for tools and resources
        using async API."""

        # Parse command and arguments
        command = self.command
        args = json.loads(self.args) if self.args else []
        env_vars = json.loads(self.env_vars) if self.env_vars else None

        # Log the command that will be executed
        _logger.info(
            "Connecting to MCP server with command: %(command)s %(args)s",
            {"command": command, "args": " ".join(args)},
        )

        # Test the command and capture stderr for better error reporting
        stderr_message = self._test_mcp_command(command, args, env_vars)

        # Create server parameters
        server_params = StdioServerParameters(command=command, args=args, env=env_vars)

        tools = []
        resources = []

        try:
            # Connect to the server via stdio
            async with stdio_client(server_params) as (read, write):
                # Log successful connection
                _logger.info("Successfully established stdio connection to MCP server")

                try:
                    async with ClientSession(read, write) as session:
                        # Initialize the connection
                        init_result = await session.initialize()
                        _logger.info("Successfully initialized MCP session")

                        # Store server capabilities
                        if hasattr(init_result, "serverInfo") and hasattr(
                            init_result.serverInfo, "capabilities"
                        ):
                            capabilities = init_result.serverInfo.capabilities
                            self.write({"capabilities": json.dumps(capabilities)})

                        # Get tools, resources, and prompts
                        tools = await self._get_tools_from_session(session)
                        resources = await self._get_resources_from_session(session)
                        prompts = await self._get_prompts_from_session(session)
                except Exception as e:
                    _logger.exception(
                        "Error during MCP session: %(error)s", {"error": str(e)}
                    )

                    # Use the stderr message captured during the test if available
                    final_message = stderr_message if stderr_message else str(e)
                    is_config_error = self._is_configuration_error(final_message)

                    # Update server state to error
                    self.write({"state": "error", "error_message": final_message})

                    # Provide more specific error message based on error type
                    if is_config_error:
                        raise UserError(
                            _(
                                "MCP Server %(name)s Configuration Error: %(message)s\n"
                                "Please check your server configuration and required "
                                "environment variables."
                            )
                            % {"name": self.name, "message": final_message}
                        ) from None
                    else:
                        raise UserError(
                            _("MCP Server %(name)s Error: %(message)s")
                            % {"name": self.name, "message": final_message}
                        ) from None
        except Exception as e:
            _logger.exception(
                "Error connecting to MCP server: %(error)s", {"error": str(e)}
            )
            # Check if it's a network-related error
            if "EAI_AGAIN" in str(e) or "getaddrinfo" in str(e):
                raise UserError(
                    _(
                        "Network error connecting to MCP server. Please check your \
                            internet connection and proxy settings."
                    )
                ) from None

            # Check if it's a UserError (already formatted with stderr)
            if isinstance(e, UserError):
                raise

            # For other errors, try to provide more context
            error_message = str(e)
            is_config_error = self._is_configuration_error(error_message)

            # Update server state to error
            self.write({"state": "error", "error_message": error_message})

            if "Connection closed" in error_message:
                if is_config_error:
                    raise UserError(
                        _(
                            "MCP Server %(name)s Configuration Error: Server closed "
                            "connection. Please check server configuration and required "
                            "environment variables."
                        )
                        % {"name": self.name}
                    ) from None
                else:
                    raise UserError(
                        _(
                            "MCP Server %(name)s Error: Server closed connection "
                            "unexpectedly. Please check server configuration and required "
                            "environment variables."
                        )
                        % {"name": self.name}
                    ) from None

            if is_config_error:
                raise UserError(
                    _(
                        "MCP Server %(name)s Configuration Error: %(error)s\n"
                        "Please check your server configuration and required "
                        "environment variables."
                    )
                    % {"name": self.name, "error": str(e)}
                ) from None

            raise UserError(
                _("Error connecting to MCP server: %(error)s") % {"error": str(e)}
            ) from None

        return tools, resources, prompts

    def _run_async_in_thread(self, coro):
        """Run an async coroutine in a new event loop in the current thread."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        except Exception as e:
            # Re-raise UserError as-is (already formatted)
            if isinstance(e, UserError):
                raise
            # For other errors, wrap them
            raise UserError(
                _("MCP Server %(name)s Error: %(error)s")
                % {"name": self.name, "error": str(e)}
            ) from None
        finally:
            loop.close()

    def _get_tools_from_server(self):
        """Get the list of tools from the MCP server using the MCP SDK."""
        _logger.info("Getting tools from server %s", self.name)

        try:
            # Run the async function in a synchronous context
            tools, _, _ = self._run_async_in_thread(self._async_connect_and_query_mcp())
            return tools
        except Exception as e:
            _logger.exception(
                "Error getting tools from server %s: %s", self.name, str(e)
            )
            return []

    def _get_resources_from_server(self):
        """Get the list of resources from the MCP server using the MCP SDK."""
        _logger.info("Getting resources from server %s", self.name)

        try:
            # Run the async function in a synchronous context
            _, resources, _ = self._run_async_in_thread(
                self._async_connect_and_query_mcp()
            )
            return resources
        except Exception as e:
            _logger.exception(
                "Error getting resources from server %s: %s", self.name, str(e)
            )
            return []

    def _get_prompts_from_server(self):
        """Get the list of prompts from the MCP server using the MCP SDK."""
        _logger.info("Getting prompts from server %s", self.name)

        try:
            # Run the async function in a synchronous context
            _, _, prompts = self._run_async_in_thread(
                self._async_connect_and_query_mcp()
            )
            return prompts
        except Exception as e:
            _logger.exception(
                "Error getting prompts from server %s: %s", self.name, str(e)
            )
            return []

    def _refresh_tools_and_resources(self):
        """Refresh tools, resources, and prompts from the MCP server."""
        _logger.info(
            "Refreshing tools, resources, and prompts for server %s", self.name
        )

        if self.state != "running":
            _logger.warning(
                "Cannot refresh tools and resources: server %s is not running",
                self.name,
            )
            return

        try:
            self._refresh_tools()
            self._refresh_resources()
            self._refresh_prompts()
        except Exception as e:
            _logger.exception(
                "Error refreshing tools and resources for server %s: %s",
                self.name,
                str(e),
            )
            error_message = self._handle_refresh_error(e)
            # Re-raise the error so it can be caught by action_start
            raise UserError(error_message) from None
