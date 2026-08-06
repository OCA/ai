To install and run this module you need the following Python packages
(installed with ``pip``):

* `paddleocr>=2.7.0,<3.0.0`
* `paddlepaddle`
* `pdf2image`
* `rapidfuzz`
* `opencv-python-headless`

And the system packages:

* `libgl1`
* `libglib2.0-0`
* `poppler-utils`

A running OpenAI-compatible chat completions endpoint is required, for example
Ollama (`http://ollama:11434/v1`) with a small instruct model such as
`qwen3:4b`.
