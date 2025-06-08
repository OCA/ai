## Prerequisites

1. **Queue Job Configuration**: Make sure to set the **agents_communication_channel** in the Odoo configuration to enable background processing as follows:
  ```
  [queue_job]
  channels = (your_channels:your_assigned_workers),root.agents_communication_channel:(assign_some_workers_here)
  ```

## AI Agent Setup

### Basic Configuration

1. Navigate to **Settings** → **Manage Users**
2. Select or create a user that will act as an AI agent
3. Go to the **Preferences** tab
4. Check **Is AI Agent** to enable agent functionality

## API Configuration

### API Type
Currently supports only **Custom API** type, which allows connection to your own API endpoints (e.g. automation frameworks, or custom APIs). This module was created in shuch a way it allows to use other API types such as OpenAI, HuggingFace, Anthropic, etc.

### API Configuration

Create a configuration by setting up API parameters defining what information it's going to be available for the agent during the request:

**Fields description:**
- **Parameter Type**:
  - **Sender Partner**: It refers to the partner related to the user has sent the message
  - **Receiver Partner**: It refers to the partner related to the user has received the message (the agent in this case)
  - **General Context**: It refers to `self`, in this case from the `discuss.channel` context. This could be useful for passing general contextual information.
- **Name**: Name for this parameter
- **Value**: The actual information the agent will use.

  - Use curly braces `{}` for dynamic values. (e.g. `{object.name}` for object.name, `{objet.env["product.product"].search([]).mapped("name")}` for passing all product names, etc.)

  - Without braces: Agent receives literal text

**Example Parameters:**
```
Name: user_name
Value: {object.name}
Parameter Type: Sender Partner
```
This configuration provides the agent with access to the sender partner's name during the request.

```
Name: agent_email
Value: {object.email}
Parameter Type: Receiver Partner
```
This configuration provides the agent with access to email of its own partner  during the request.

```
Name: context_companies
Value: {object.env['res.company'].search([]).mapped('name')}
Parameter Type: Receiver Partner
```
This configuration provides the agent with the list of companies during the request.

### API Endpoint
The endpoint of your custom API

### Authentication Type:
- **None**: No authentication required
- **Header Token**: Uses Bearer Authentication, internally this header is added to the request `Authorization: Bearer whateverTokenUserSetOnTheAgentConfiguration`

### API Timeout
- **API Timeout**: Maximum time (in seconds) to wait for API response (default: 30)

### Request Method:
- **POST** (default)
- **GET**

### Response Key:
Specifies which field in the API response contains the agent's message.

Example: If set to "response", the API response should include: `{"response": "Agent message here"}`

## UX Settings and extras

### Simulated Delay
- **Simulated Delay**: Enable artificial response delays, this is useful when working with very fast agents (in livechat for example). Some users prefer the human-like feedback of "thinking" or "typing" instead of asking for something and getting a response right away. **Notice:** if the agent response takes longer than the simulated delay, delay will be invalidated and the response will go straight to the chat.
- **Min/Max Delay**: Range for simulated delays in seconds

### Extras
- **Agent Category**: Organize agents by category for better management

## Example Complete Configuration

1. **User Setup**: Create user "Customer Support Agent"
2. **Enable Agent**: Check "Is AI Agent"
3. **API Configuration**:
   - Name: "Customer Support Config"
   - Parameters:
     - user_name: `{object.name}` (Sender Partner)
     - agent_category: `{object.user_id.agent_category_id.name}` (Receiver Partner)
     - name_all_product: `{objet.env["product.product"].search([]).mapped("name")}` (General Context)
4. **API Settings**:
   - API endpoint: `https://your-api.com/agent`
   - API Method: POST
   - Authentication Type: Header Token
   - HeaderAuth Token: your_token
   - Response Key: your_response_key

This configuration enables a customer support agent that knows the customer's name, its own identity, and has access to product information.

## Other considerations
An **AI Agent** remains always active. This is handled by a cron job called *Keep AI Agents online status*
