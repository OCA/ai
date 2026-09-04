To install and run this module you need the following Python packages
(installed with ``pip``):

* `Pillow`
* `pdf2image`
* `rapidfuzz`
* `requests`

And the system package:

* `poppler-utils` (required by `pdf2image` to render PDFs)

A running OpenAI-compatible chat completions endpoint with a vision model is
required, for example Ollama (`http://ollama:11434/v1`) running a vision model
such as `qwen3-vl`, or a cloud provider such as OpenRouter
(`https://openrouter.ai/api/v1`).
