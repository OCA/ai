1. Go to *Accounting > Vendors > Bills* and create a draft vendor bill (or open an
   existing draft one).
2. Attach the invoice PDF or image to the chatter.
3. Click **Extract with AI**. The invoice is processed in the background.
4. When the *AI Extraction State* becomes *Done*, check the extracted values. The
   partner is set automatically when a match is found.
5. If the partner could not be matched, click **Review Extraction** and pick or
   create the partner in the wizard.

Configure the AI backend as follows:

1. Create an *AI Connection* under *Settings > AI > AI Connection* with kind
   **OpenAI-compatible**:
   - Set the URL to a cloud provider such as `https://openrouter.ai/api/v1` or to
     a local Ollama server like `http://localhost:11434/v1`.
   - Set the model, e.g. `qwen/qwen3-vl-32b-instruct` for OpenRouter or
     `qwen3-vl:8b` for Ollama.
   - Set the API key for cloud providers only (leave it empty for local Ollama)
     and set the temperature to 0. For Ollama you can also set the *Ollama Context
     Window* and *Ollama Keep Alive*.
2. Link the connection under *Settings > Technical > AI > AI Document
   Extraction* in the *AI Connection* field (developer mode is required to see
   the Technical menu). The partner match threshold can also be set there.

The extraction flow is unchanged: upload the invoice, then click **Extract with
AI**.
