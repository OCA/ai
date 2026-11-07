# Copyright 2025 Pierre Verkest
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

from openai import LengthFinishReasonError, OpenAI

from odoo import api, models

_logger = logging.getLogger(__name__)


class AiLlmClient(models.AbstractModel):
    """
    Abstract model to provide a simple Python client setup for an Open LLM connection.
    It resolves configuration dynamically and performs the completions calls.
    """

    _name = "ai.llm.client"
    _description = "AI LLM Client Wrapper"

    @api.model
    def _get_client(self, model_type: str = "fast"):
        config_param = self.env["ir.config_parameter"].sudo()
        url = config_param.get_param(
            f"ai_llm.{model_type}_base_url"
        ) or config_param.get_param(
            "ai_llm.base_url", "http://localhost:11434/v1"
        )
        api_key = config_param.get_param("ai_oca_native_llm.api_key")
        return OpenAI(base_url=url, api_key=api_key)

    @api.model
    def _get_default_models_type(self):
        return {
            "fast": "llama3.2",
            "reasoning": "llama3",
            "decision": "decision",
        }

    @api.model
    def _get_model(self, model_type: str):
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                f"ai_llm.{model_type}_model",
                self._get_default_models_type().get(model_type, "llama3.2"),
            )
        )

    @api.model
    def chat(
        self,
        messages,
        model_type="fast",
        model: str = None,
        options=None,
        response_model=None,
        tools=None,
        tool_choice=None,
    ):
        """Sends a chat request via OpenAI-compatible endpoint.

        :param messages: list of dicts [{'role': 'user', 'content': 'hello'}, ...]
        :param model_type: 'reasoning' or 'fast'
        :param model: LLM model to use.
        :param options: dict of optional parameters (e.g. temperature, response_format)
        :param response_model: optional Pydantic Base Model class to parse
               the response into
        :param tools: optional list of tool definition dicts for OpenAI function calling
        :param tool_choice: optional tool choice directive (e.g. 'auto', 'none', 'required')
        :return: string response content, or structured dict with 'content' and 'tool_calls' if tools is provided, or None if request fails
        """
        client = self._get_client(model_type=model_type)
        if not model:
            model = self._get_model(model_type)

        if not options:
            options = {}
        if tools is not None:
            options["tools"] = tools
        if tool_choice is not None:
            options["tool_choice"] = tool_choice

        try:
            _logger.info("LLM context and question: %s", messages)
            if response_model:
                response = client.beta.chat.completions.parse(
                    model=model,
                    messages=messages,
                    response_format=response_model,
                    **options,
                )
            else:
                response = client.chat.completions.create(
                    model=model, messages=messages, **options
                )
            msg = response.choices[0].message
            _logger.info("LLM Response: %s", msg.content)
            if tools is not None:
                tool_calls_data = []
                for tc in getattr(msg, "tool_calls", None) or []:
                    tool_calls_data.append(
                        {
                            "id": getattr(tc, "id", None),
                            "type": getattr(tc, "type", "function"),
                            "function": {
                                "name": getattr(tc.function, "name", ""),
                                "arguments": getattr(tc.function, "arguments", "{}"),
                            },
                        }
                    )
                return {
                    "content": msg.content,
                    "tool_calls": tool_calls_data,
                }
            return msg.content
        except LengthFinishReasonError as err:
            _logger.warning(
                "LLM completion truncated (context length limit reached): %s", err
            )
            return None
        except Exception as err:
            _logger.exception("LLM API completion failed: %s", err)
            return None

    @api.model
    def _serialize_decision_answer(self, answer) -> dict:
        answer_type = getattr(answer, "type", None)
        name = getattr(answer, "name", None)
        if answer_type == "choice":
            return {
                "name": name,
                "type": "choice",
                "choice": getattr(answer, "choice", None),
                "confidence": getattr(answer, "confidence", 0.0),
                "probabilities": [
                    {
                        "value": getattr(prob, "value", None),
                        "probability": getattr(prob, "probability", 0.0),
                    }
                    for prob in (getattr(answer, "probabilities", None) or [])
                ],
            }
        if answer_type == "predicate":
            return {
                "name": name,
                "type": "predicate",
                "probability": getattr(answer, "probability", 0.0),
            }
        if answer_type == "score":
            return {
                "name": name,
                "type": "score",
                "score": getattr(answer, "score", 0.0),
                "confidence": getattr(answer, "confidence", 0.0),
                "probabilities": [
                    {
                        "label": getattr(prob, "label", ""),
                        "value": getattr(prob, "value", 0),
                        "probability": getattr(prob, "probability", 0.0),
                    }
                    for prob in (getattr(answer, "probabilities", None) or [])
                ],
            }
        return {
            "name": name,
            "type": "refusal",
        }

    @api.model
    def decide(
        self,
        input_data,
        questions: list[dict],
        model: str | None = None,
        options: dict | None = None,
    ) -> list[dict] | None:
        """Evaluate structured System 1 questions via the OpenAI Decisions API.

        :param input_data: string or list of message/tool items to evaluate
        :param questions: list of question dicts ('choice', 'predicate', 'score')
        :param model: optional explicit decision model name
        :param options: optional extra keyword arguments for client.decisions.create
        :return: list of serialized answer dicts in question order, or None on error
        """
        client = self._get_client(model_type="decision")
        if not model:
            model = self._get_model("decision")
        extra_options = dict(options) if options else {}

        try:
            _logger.info("Decision input: %s | questions: %s", input_data, questions)
            response = client.decisions.create(
                model=model,
                input=input_data,
                questions=questions,
                **extra_options,
            )
            answers = [
                self._serialize_decision_answer(ans)
                for ans in (getattr(response, "answers", None) or [])
            ]
            _logger.info("Decision answers: %s", answers)
            return answers
        except Exception as err:
            _logger.exception("LLM Decisions API call failed: %s", err)
            return None

    @api.model
    def decide_choice(
        self,
        input_data,
        choices: list[dict],
        instructions: str,
        name: str = "next_action",
        model: str | None = None,
        options: dict | None = None,
    ) -> dict | None:
        """Evaluate a single categorical choice question with the System 1 Decision Model.

        :param input_data: string or list of conversation items to evaluate
        :param choices: list of candidate dicts [{'value': '...', 'description': '...'}, ...]
        :param instructions: instructions guiding the choice selection
        :param name: question identifier (default 'next_action')
        :param model: optional explicit decision model name
        :param options: optional extra keyword arguments for client.decisions.create
        :return: serialized choice answer dict if a choice was selected, or None on refusal/error
        """
        question = {
            "name": name,
            "type": "choice",
            "instructions": instructions,
            "choices": choices,
        }
        answers = self.decide(
            input_data=input_data,
            questions=[question],
            model=model,
            options=options,
        )
        if not answers:
            return None
        first_answer = answers[0]
        if first_answer.get("type") != "choice":
            return None
        return first_answer
