#!/usr/bin/env python3
"""
Hermes Odoo Gateway - Standalone client with AIAgent integration.

This script connects a running Hermes AIAgent to an Odoo instance
with the ai_oca_bridge_hermes module installed.

Usage:
    # Standalone mode (for testing)
    python hermes_odoo_gateway.py \
        --odoo-url http://localhost:8069 \
        --webhook-token YOUR_TOKEN \
        --poll-interval 5

    # With AIAgent (full Hermes with tools)
    python hermes_odoo_gateway.py \
        --odoo-url http://localhost:8069 \
        --webhook-token YOUR_TOKEN \
        --use-agent \
        --model kimi-k2.6 \
        --provider kimi-coding

Author: Akretion (2026)
License: AGPL-3.0
"""

import argparse
import asyncio
import html
import logging
import os
import re
import sys

import httpx

# Setup logging FIRST (before any logger usage)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("hermes_odoo")

# Load Hermes .env before anything else
HERMES_DOTENV = os.path.expanduser("~/.hermes/.env")
if os.path.exists(HERMES_DOTENV):
    import dotenv

    # Load .env but don't override existing env vars (user's shell takes precedence)
    dotenv.load_dotenv(HERMES_DOTENV, override=False)
    logger.debug(f"Loaded env from {HERMES_DOTENV}")

# Add Hermes agent to path
HERMES_AGENT_DIR = os.path.expanduser("~/.hermes/hermes-agent")
if HERMES_AGENT_DIR not in sys.path:
    sys.path.insert(0, HERMES_AGENT_DIR)


def get_ai_agent(session_key: str, **kwargs):
    """Create an AIAgent instance for a session.

    This imports Hermes AIAgent and creates a configured instance.
    """
    try:
        from run_agent import AIAgent
    except ImportError as e:
        logger.error(f"Cannot import AIAgent: {e}")
        logger.error(f"Make sure {HERMES_AGENT_DIR} is in your PYTHONPATH")
        raise

    # Fix Kimi base URL: add /v1 suffix for OpenAI SDK compatibility
    # (Hermes CLI uses Anthropic SDK which handles this differently)
    base_url = os.environ.get("KIMI_BASE_URL", "")
    if base_url and base_url.rstrip("/").endswith("/coding"):
        os.environ["KIMI_BASE_URL"] = base_url.rstrip("/") + "/v1"
        logger.debug(
            f"Fixed KIMI_BASE_URL for OpenAI SDK: {os.environ['KIMI_BASE_URL']}"
        )

    # Build agent with sensible defaults for Odoo integration
    logger.info(
        "Creating AIAgent with session_id=%s, model=%s, provider=%s",
        session_key,
        kwargs.get("model", ""),
        kwargs.get("provider", None),
    )
    agent = AIAgent(
        session_id=session_key,
        platform="odoo",
        # Inherit model/provider from Hermes config if not specified
        model=kwargs.get("model", ""),
        provider=kwargs.get("provider", None),
        # Limit iterations for safety
        max_iterations=kwargs.get("max_iterations", 30),
        # Enable useful toolsets, disable dangerous ones
        enabled_toolsets=kwargs.get("enabled_toolsets", None),
        disabled_toolsets=kwargs.get("disabled_toolsets", None) or ["computer_use"],
        # Don't be too verbose
        quiet_mode=True,
        # Skip loading context files to speed up
        skip_context_files=True,
        # Load memory for cross-session continuity
        skip_memory=False,
    )
    logger.info("AIAgent created successfully")
    return agent


class OdooGatewayClient:
    """Client that polls Odoo for messages and forwards responses."""

    def __init__(
        self,
        odoo_url: str,
        webhook_token: str,
        poll_interval: int = 5,
        timeout: int = 30,
        use_agent: bool = False,
        agent_kwargs: dict = None,
    ):
        self.odoo_url = odoo_url.rstrip("/")
        self.webhook_token = webhook_token
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.running = False
        self._client: httpx.AsyncClient | None = None
        self._use_agent = use_agent
        self._agent_kwargs = agent_kwargs or {}
        # Cache AIAgent instances per session
        self._agents: dict = {}

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def start(self):
        """Main polling loop."""
        self.running = True
        logger.info(f"Starting Odoo gateway client for {self.odoo_url}")
        logger.info(f"Polling every {self.poll_interval} seconds")
        if self._use_agent:
            logger.info(
                "AIAgent mode enabled - Hermes will process messages with tools"
            )
        else:
            logger.info(
                "Echo mode - messages will be echoed back (use --use-agent for AI)"
            )

        while self.running:
            try:
                messages = await self._poll_messages()
                for msg in messages:
                    await self._process_message(msg)
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Poll error: {e}")
                await asyncio.sleep(self.poll_interval * 2)

    async def stop(self):
        """Stop the polling loop."""
        self.running = False
        logger.info("Stopping Odoo gateway client")

    async def _poll_messages(self) -> list:
        """Fetch pending messages from Odoo."""
        url = f"{self.odoo_url}/hermes/poll"
        headers = {"Authorization": f"Bearer {self.webhook_token}"}

        try:
            resp = await self._client.post(url, headers=headers, json={})
            resp.raise_for_status()
            data = resp.json()
            # Handle Odoo JSON-RPC response structure
            if isinstance(data, dict):
                if "error" in data:
                    logger.warning(f"Odoo poll error: {data['error']}")
                    return []
                # JSON-RPC wraps result in "result" key
                result = data.get("result", {})
                if isinstance(result, dict):
                    return result.get("messages", [])
                return result if isinstance(result, list) else []
            return []
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error polling Odoo: {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Error polling Odoo: {e}")
            return []

    async def _process_message(self, msg: dict):
        """Process a single message from Odoo."""
        channel_id = msg.get("channel_id")
        body = msg.get("body", "")
        author_name = msg.get("author_name", "User")
        db_hash = msg.get("db_hash", "unknown")

        # Build session key
        session_key = f"odoo:{db_hash}:channel_{channel_id}"

        # Strip HTML from body
        text = self._strip_html(body)
        if not text:
            return

        logger.info(f"Processing message from {author_name} in channel {channel_id}")

        # Get or create AIAgent for this session
        if self._use_agent:
            response = await self._get_agent_response(session_key, text, author_name)
        else:
            # Echo mode for testing
            response = f"Echo: {text}"

        # Send response back to Odoo
        self._send_response(channel_id, response)

    async def _get_agent_response(
        self, session_key: str, text: str, author_name: str
    ) -> str:
        """Get response from Hermes AIAgent.

        Creates or reuses an AIAgent per session for conversation continuity.
        """
        # Get or create agent for this session
        if session_key not in self._agents:
            try:
                self._agents[session_key] = get_ai_agent(
                    session_key, **self._agent_kwargs
                )
            except Exception as e:
                logger.error(f"Failed to create AIAgent: {e}")
                return f"Sorry, I couldn't initialize my AI brain. Error: {e}"

        # Build user message with author context
        user_message = f"[{author_name}] {text}"

        agent = self._agents.get(session_key)
        if not agent:
            return "Error: AI agent not available"

        # Run agent (sync method, run in thread pool)
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,  # default executor
                lambda: agent.chat(user_message),
            )
            return response
        except Exception as e:
            logger.exception("Agent error:")
            return f"I encountered an error while processing your message: {e}"

    def _send_response(self, channel_id: int, response: str):
        """Send response back to Odoo channel."""
        url = f"{self.odoo_url}/hermes/webhook/{self.webhook_token}"
        payload = {
            "channel_id": channel_id,
            "body": response,
        }

        try:
            resp = self._client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            # Handle Odoo JSON-RPC response structure
            if isinstance(data, dict):
                if "error" in data:
                    logger.warning(f"Odoo webhook error: {data['error']}")
                    return
                result = data.get("result", {})
                if isinstance(result, dict) and result.get("status") == "ok":
                    logger.info(f"Response sent to channel {channel_id}")
                else:
                    logger.warning(f"Odoo webhook returned: {data}")
            else:
                logger.warning(f"Odoo webhook returned unexpected: {data}")
        except Exception as e:
            logger.error(f"Failed to send response: {e}")

    @staticmethod
    def _strip_html(html_text: str) -> str:
        """Strip HTML tags and convert entities to plain text."""
        if not html_text:
            return ""
        text = re.sub(r"<[^>]+>", "", html_text)
        text = html.unescape(text)
        return text.strip()


async def main():
    parser = argparse.ArgumentParser(description="Hermes Odoo Gateway Client")
    parser.add_argument(
        "--odoo-url",
        default="http://localhost:8069",
        help="Odoo instance base URL",
    )
    parser.add_argument(
        "--webhook-token",
        required=True,
        help="Webhook token from Odoo Hermes Gateway configuration",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=5,
        help="Polling interval in seconds (default: 5)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--use-agent",
        action="store_true",
        help="Use Hermes AIAgent instead of echo mode",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Model name for AIAgent (e.g., kimi-k2.6, claude-sonnet-4)",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="Provider for AIAgent (e.g., kimi-coding, anthropic)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=30,
        help="Max AIAgent iterations (default: 30)",
    )
    parser.add_argument(
        "--enabled-toolsets",
        default=None,
        help="Comma-separated toolsets to enable (e.g., web,terminal,file)",
    )
    parser.add_argument(
        "--disabled-toolsets",
        default="computer_use",
        help="Comma-separated toolsets to disable (default: computer_use)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Build agent kwargs
    agent_kwargs = {
        "model": args.model or "k2p6",
        "provider": args.provider
        or "kimi-coding",  # Maps to kimi-for-coding internally
        "max_iterations": args.max_iterations,
    }
    if args.enabled_toolsets:
        agent_kwargs["enabled_toolsets"] = args.enabled_toolsets.split(",")
    if args.disabled_toolsets:
        agent_kwargs["disabled_toolsets"] = args.disabled_toolsets.split(",")

    client = OdooGatewayClient(
        odoo_url=args.odoo_url,
        webhook_token=args.webhook_token,
        poll_interval=args.poll_interval,
        timeout=args.timeout,
        use_agent=args.use_agent,
        agent_kwargs=agent_kwargs,
    )

    async with client:
        try:
            await client.start()
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
