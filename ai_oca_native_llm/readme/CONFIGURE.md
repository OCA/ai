To configure this module, go to **Settings > Native AI > LLM API Configuration** or set the following `ir.config_parameter` entries:

| Parameter Key | Default | Description |
|---|---|---|
| `ai_llm.base_url` | `http://localhost:11434/v1` | Primary OpenAI-compatible API endpoint (recommended: LiteLLM Proxy Gateway at `http://localhost:4000/v1`) |
| `ai_oca_native_llm.api_key` | *(empty)* | Bearer API key (`none` for local proxy/vLLM) |
| `ai_llm.decision_model` | `decision` | System 1 Decision model name used by `decide()` / `decide_choice()` (`POST /v1/decisions`) |
| `ai_llm.fast_model` | `llama3.2` | Fast System 2 generative model (`POST /v1/chat/completions`) |
| `ai_llm.reasoning_model` | `llama3` | Reasoning System 2 generative model (`POST /v1/chat/completions`) |
| `ai_llm.<model_type>_base_url` | *(optional)* | Optional per-model-type endpoint override (`ai_llm.decision_base_url`, `ai_llm.fast_base_url`, `ai_llm.reasoning_base_url`) if not using a unified gateway |

## Recommended Architecture: LiteLLM Gateway + Dual vLLM

Rather than configuring multiple URLs inside Odoo, the recommended architecture places a single **LiteLLM Proxy** in front of your inference engines. LiteLLM natively exposes `/v1/decisions` and `/v1/chat/completions` and automatically translates OpenAI Decisions requests (`/v1/decisions`) to vLLM's native System One endpoint (`/v1/systemone`).

### 1. Start the System 1 Decision Model (`vllm >= 0.32.0`, port 8001, ~2 GB VRAM)
```bash
CUDA_VISIBLE_DEVICES=0 vllm serve vllm-sr/d3-edge \
  --port 8001 \
  --gpu-memory-utilization 0.25 \
  --max-model-len 4096
```

### 2. Start the System 2 Generative LLM (port 8000, ~4.9 GB VRAM)
```bash
CUDA_VISIBLE_DEVICES=0 vllm serve Qwen/Qwen2.5-1.5B-Instruct \
  --port 8000 \
  --gpu-memory-utilization 0.60 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes \
  --max-model-len 12000
```

### 3. Start the LiteLLM Gateway (`config.yaml` on port 4000)
```yaml
model_list:
  - model_name: decision
    litellm_params:
      model: hosted_vllm/vllm-sr/d3-edge
      api_base: http://localhost:8001/v1
      api_key: none
  - model_name: fast
    litellm_params:
      model: hosted_vllm/Qwen/Qwen2.5-1.5B-Instruct
      api_base: http://localhost:8000/v1
      api_key: none
  - model_name: reasoning
    litellm_params:
      model: hosted_vllm/Qwen/Qwen2.5-1.5B-Instruct
      api_base: http://localhost:8000/v1
      api_key: none
```
