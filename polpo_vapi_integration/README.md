# Voice Agent with AI for Odoo – Vapi Integration

This module enables seamless Vapi.ai AI voice agent integration in Odoo, with out-of-the-box support.
Call your voice AI agent created in Vapi.ai with Odoo to manage customer interactions, create leads,
and log calls directly from your Odoo instance.

## 🚀 Key Features

- Create and update leads, customers, and opportunities using voice commands
- Hands-free querying of CRM, agenda, calls, and activities
- Automatic call logs and transcription inside Odoo
- Per-user API key management and secure access
- Supports Spanish (Uy) and multilingual voice commands
- Compatible with Odoo 16 (Community and Enterprise)

## 🎯 Use Cases

- Sales teams making fast call-entry without typing
- Customer support updating records by voice
- Managers reviewing call logs and summaries effortlessly
- Developers extending voice flows to other Odoo modules

## ✅ Benefits

- Accelerates data entry — speak instead of type
- Improves productivity and reduces manual errors
- Centralizes voice interactions and CRM insights
- Open source — fully customizable for your flows and logic

## ✅ Looking for a complete voice integration with Odoo or for other Editions?

This module is a connector for Vapi.ai, designed to help you get started with voice automation in Odoo Community.

If you need a **fully customized voice agent** that integrates with CRM, Sales, Purchases,
Inventory or any other Odoo module (including registering and consulting data by voice), we can help!

**Contact us:**
info@polpo.uy

Also for other Odoo versions and editions (Enterprise, Online, etc.).

We offer tailored implementations for your business needs. Ask us about advanced voice workflows
and seamless integration with your Odoo database.

## ⚙️ Configuration

1. **Install the module** in your Odoo Community instance.

   > ⚠️ **IMPORTANT:** This module makes changes to the `res.users` model.
   > After installing, you **must update the module from the command line** to apply all changes correctly.
   >
   > Run:
   > ```bash
   > odoo -u YOUR_MODULE_NAME -d YOUR_DATABASE_NAME
   > ```
   > *(Replace `YOUR_MODULE_NAME` and `YOUR_DATABASE_NAME` accordingly)*

2. **Go to Settings > Vapi Integration** and configure your Vapi.ai credentials:
  - Set your **Vapi API Key** and **Assistant ID**.
3. **Assign a unique Vapi API Key** to each user (from user preferences).
4. Just click the **call button** in Odoo to start interacting by voice!
5. All calls and interactions are automatically logged and visible in the **Vapi > Logs** menu for review and audit.

