"""The tool-using Claude agent: a manual Messages API loop with guard rails.

Written as a manual loop rather than a tool runner because the loop itself holds safety logic:
tool budgets, the verified-weather gate, and output validation with a bounded correction.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import anthropic
from pydantic import ValidationError

from app.agents.output import FINAL_OUTPUT_SCHEMA, AgentFinalOutput, contains_dosage
from app.agents.prompts import STATIC_SYSTEM_PROMPT
from app.core.config import Settings
from app.core.errors import AgentError, AgentNotConfiguredError, AgentTimeoutError
from app.intelligence.recommendation import weather_context_from_snapshot
from app.intelligence.types import (
    WEATHER_DEPENDENT_INTENTS,
    Confidence,
    FarmingAdvice,
    Intent,
    RiskLevel,
)
from app.tools.base import ToolContext, ToolRegistry

logger = logging.getLogger("farmagent.agent")

EventSink = Callable[[dict], Awaitable[None]]

_WEATHER_MISSING = "Verified weather for this location"


@dataclass
class AgentResult:
    advice: FarmingAdvice
    tool_log: list[dict] = field(default_factory=list)
    iterations: int = 0
    tool_calls: int = 0


async def _no_events(_: dict) -> None:
    return None


class FarmAgent:
    def __init__(self, client: Any | None, settings: Settings, registry: ToolRegistry) -> None:
        self._client = client
        self._settings = settings
        self._registry = registry

    @property
    def is_unconfigured(self) -> bool:
        return self._client is None

    async def run(
        self,
        *,
        user_message: str,
        context_block: str,
        context: ToolContext,
        history: list[dict] | None = None,
        emit: EventSink = _no_events,
    ) -> AgentResult:
        if self._client is None:
            raise AgentNotConfiguredError()
        try:
            async with asyncio.timeout(self._settings.agent_total_timeout_seconds):
                return await self._loop(user_message, context_block, context, history or [], emit)
        except TimeoutError:
            logger.warning("agent exceeded total timeout")
            raise AgentTimeoutError() from None

    async def _loop(
        self,
        user_message: str,
        context_block: str,
        context: ToolContext,
        history: list[dict],
        emit: EventSink,
    ) -> AgentResult:
        system = [
            {
                "type": "text",
                "text": STATIC_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": context_block},
        ]
        messages: list[dict] = [*history, {"role": "user", "content": user_message}]
        tool_log: list[dict] = []
        tool_calls = 0
        corrections = 0
        settings = self._settings

        for iteration in range(1, settings.agent_max_iterations + 1):
            budget_spent = tool_calls >= settings.agent_max_tool_calls
            final_turn = iteration == settings.agent_max_iterations
            await emit({"type": "status", "stage": "thinking", "iteration": iteration})
            response = await self._call_model(
                system, messages, allow_tools=not (budget_spent or final_turn)
            )
            stop = response.stop_reason

            if stop == "tool_use":
                tool_uses = [b for b in response.content if b.type == "tool_use"]
                messages.append({"role": "assistant", "content": response.content})
                results = []
                for block in tool_uses:
                    if tool_calls >= settings.agent_max_tool_calls:
                        results.append(_budget_exhausted_block(block.id))
                        continue
                    tool_calls += 1
                    await emit({"type": "tool_start", "id": block.id, "name": block.name})
                    outcome = await self._registry.execute(
                        block.id, block.name, block.input, context
                    )
                    results.append(outcome.tool_result_block())
                    tool_log.append(outcome.log_entry(block.input))
                    await emit(
                        {
                            "type": "tool_end",
                            "id": block.id,
                            "name": block.name,
                            "ok": outcome.ok,
                            "duration_ms": outcome.duration_ms,
                            "error_code": outcome.error_code,
                            "provenance": outcome.provenance,
                        }
                    )
                messages.append({"role": "user", "content": results})
                continue

            if stop == "refusal":
                logger.info("model refused request")
                return self._result(
                    self._fallback(
                        context,
                        "I can't help with that request. Try asking about your crop, irrigation or "
                        "the weather on your farm.",
                    ),
                    tool_log,
                    iteration,
                    tool_calls,
                )

            text = "".join(b.text for b in response.content if b.type == "text")
            output, problem = _parse_output(text) if stop != "max_tokens" else (None, "truncated")
            if output is not None and problem is None:
                problem = self._check_rules(output, context)

            if problem is None:
                return self._result(
                    self._finalize(output, context), tool_log, iteration, tool_calls
                )

            logger.info("agent output rejected problem=%s corrections=%s", problem, corrections)
            if corrections >= 2 or final_turn:
                if output is not None:
                    return self._result(
                        self._force_safe(output, context, problem), tool_log, iteration, tool_calls
                    )
                break
            corrections += 1
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": _CORRECTIONS[problem]})

        logger.warning("agent ended without a usable answer tool_calls=%s", tool_calls)
        return self._result(
            self._fallback(
                context,
                "I could not finish working this out within my limits for one question. "
                "Try asking something more specific.",
            ),
            tool_log,
            settings.agent_max_iterations,
            tool_calls,
        )

    async def _call_model(
        self, system: list[dict], messages: list[dict], *, allow_tools: bool
    ) -> Any:
        settings = self._settings
        params: dict[str, Any] = {
            "model": settings.anthropic_model,
            "max_tokens": settings.anthropic_max_tokens,
            "system": system,
            "messages": messages,
            "tools": self._registry.definitions(),
            "output_config": {"format": {"type": "json_schema", "schema": FINAL_OUTPUT_SCHEMA}},
        }
        if not allow_tools:
            params["tool_choice"] = {"type": "none"}
        if settings.anthropic_adaptive_thinking:
            params["thinking"] = {"type": "adaptive"}
        try:
            return await self._client.messages.create(**params)
        except anthropic.APITimeoutError:
            logger.warning("anthropic request timed out")
            raise AgentTimeoutError() from None
        except anthropic.AuthenticationError:
            logger.error("anthropic rejected the configured API key")
            raise AgentError(
                "The AI assistant's API key was rejected.", code="agent_auth_failed"
            ) from None
        except anthropic.RateLimitError:
            logger.warning("anthropic rate limit reached")
            raise AgentError(
                "The AI assistant is at its usage limit. Try again shortly.",
                code="agent_rate_limited",
            ) from None
        except anthropic.APIError as exc:
            logger.warning("anthropic request failed type=%s", type(exc).__name__)
            raise AgentError() from None

    def _check_rules(self, output: AgentFinalOutput, context: ToolContext) -> str | None:
        if contains_dosage(output):
            return "dosage"
        if (
            output.intent in WEATHER_DEPENDENT_INTENTS
            and not context.ledger.has_verified_weather
            and not context.ledger.failures
        ):
            return "no_weather"
        return None

    def _finalize(self, output: AgentFinalOutput, context: ToolContext) -> FarmingAdvice:
        ledger = context.ledger
        snapshot = ledger.snapshot()
        advice = FarmingAdvice(
            **output.model_dump(),
            weather_context=weather_context_from_snapshot(snapshot) if snapshot else None,
            data_sources=_data_sources(context),
            generated_by="claude_agent",
        )
        needs_weather = output.intent in WEATHER_DEPENDENT_INTENTS
        if needs_weather and not ledger.has_verified_weather:
            # Weather tools were tried and failed: the answer may explain that, but may not advise.
            advice.recommendation = None
            advice.confidence = Confidence.LIMITED
            advice.risk_level = RiskLevel.UNCERTAIN
            _add_missing(advice, _WEATHER_MISSING)
        elif needs_weather and snapshot is not None and snapshot.is_stale:
            advice.confidence = Confidence.LIMITED
            _add_missing(advice, "Up-to-date weather (the data used is out of date)")
        return advice

    def _force_safe(
        self, output: AgentFinalOutput, context: ToolContext, problem: str
    ) -> FarmingAdvice:
        """The model did not fix a rule breach after correction, so the server removes the advice."""
        if problem == "no_weather":
            return self._fallback(
                context,
                "I could not verify the weather for this location, so I am not giving a "
                "weather-dependent recommendation.",
                intent=output.intent,
            )
        return self._fallback(
            context,
            "I can't give chemical product or dose instructions. Please ask your local Krishi "
            "Vigyan Kendra or agricultural extension officer about treatment.",
            intent=output.intent,
        )

    def _fallback(
        self, context: ToolContext, summary: str, intent: Intent = Intent.GENERAL
    ) -> FarmingAdvice:
        snapshot = context.ledger.snapshot()
        advice = FarmingAdvice(
            intent=intent,
            recommendation=None,
            summary=summary,
            risk_level=RiskLevel.UNCERTAIN,
            confidence=Confidence.LIMITED,
            weather_context=weather_context_from_snapshot(snapshot) if snapshot else None,
            data_sources=_data_sources(context),
            generated_by="safety_fallback",
        )
        if not context.ledger.has_verified_weather and intent in WEATHER_DEPENDENT_INTENTS:
            _add_missing(advice, _WEATHER_MISSING)
        return advice

    @staticmethod
    def _result(
        advice: FarmingAdvice, tool_log: list, iterations: int, tool_calls: int
    ) -> AgentResult:
        return AgentResult(
            advice=advice, tool_log=tool_log, iterations=iterations, tool_calls=tool_calls
        )


_CORRECTIONS = {
    "invalid": (
        "Your last response was not valid against the required JSON schema. Return only the JSON "
        "object, with every required field."
    ),
    "truncated": (
        "Your last response was cut off for length. Return the complete JSON object again, more "
        "concisely."
    ),
    "no_weather": (
        "You gave weather-dependent advice without retrieving weather in this conversation turn. "
        "Call the appropriate weather or assessment tool now, then answer from its result. If you "
        'have no coordinates, ask the farmer for a location with intent "general".'
    ),
    "dosage": (
        "Your answer contains a chemical or product dose. Remove every dose and product instruction. "
        "Give monitoring advice and refer treatment decisions to a local extension officer."
    ),
}


def _parse_output(text: str) -> tuple[AgentFinalOutput | None, str | None]:
    try:
        return AgentFinalOutput.model_validate_json(text), None
    except ValidationError:
        return None, "invalid"


def _budget_exhausted_block(tool_use_id: str) -> dict:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "is_error": True,
        "content": json.dumps(
            {
                "error": "tool_call_limit",
                "message": "The tool budget for this question is used up. Answer from the results "
                "you already have and list anything else under missing_information.",
            }
        ),
    }


def _data_sources(context: ToolContext) -> list[str]:
    sources: list[str] = []
    snapshot = context.ledger.snapshot()
    if snapshot is not None:
        sources.append(snapshot.source)
    if context.used_engine:
        sources.append("FarmAgent decision engine")
    if context.used_crop_knowledge:
        sources.append("FarmAgent crop rule base")
    return sources


def _add_missing(advice: FarmingAdvice, item: str) -> None:
    if item not in advice.missing_information:
        advice.missing_information.append(item)
