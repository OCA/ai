## Configuration

1. Go to *AI Bridge > Hermes > Gateways* and create a new gateway
2. Select an AI User (must have an AI Bridge configured)
3. Copy the webhook token to your Hermes gateway script configuration
4. Optionally select specific channels to monitor (leave empty for all)

## Running the Gateway Script

```bash
# Basic echo mode (for testing)
python hermes_odoo_gateway.py \
    --odoo-url http://localhost:8069 \
    --webhook-token YOUR_TOKEN \
    --poll-interval 5

# With AIAgent (full Hermes with tools)
python hermes_odoo_gateway.py \
    --odoo-url http://localhost:8069 \
    --webhook-token YOUR_TOKEN \
    --use-agent \
    --model k2p6 \
    --provider kimi-coding
```

## Usage

Once configured, simply send a message in a monitored channel or DM the AI user.
Hermes will poll for messages, process them with the AI, and post responses back.

## Extending

To add custom message handlers, create a child module and override:
- `hermes_webhook._action_escalate()` for escalation logic
- `hermes_message_queue` models for custom state handling
- Gateway script handlers for custom AI processing
