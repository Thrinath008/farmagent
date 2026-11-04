"""Tool plumbing: argument validation, execution, logging and the verified-weather ledger."""

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.errors import AppError
from app.database.session import SessionFactory
from app.intelligence.types import WeatherSnapshot
from app.intelligence.weather_analysis import build_snapshot
from app.schemas.weather import CurrentWeather, Forecast
from app.services.weather import WeatherProvider

logger = logging.getLogger("farmagent.tools")

MAX_TOOL_RESULT_CHARS = 30_000


@dataclass
class WeatherLedger:
    """What weather was actually retrieved during this agent run.

    The final answer's weather context and data sources are built from this record rather than
    from anything the model wrote, so the model cannot cite weather it did not retrieve.
    """

    current: CurrentWeather | None = None
    forecast: Forecast | None = None
    failures: list[str] = field(default_factory=list)

    @property
    def has_verified_weather(self) -> bool:
        return self.current is not None or self.forecast is not None

    def snapshot(self) -> WeatherSnapshot | None:
        return build_snapshot(self.current, self.forecast)


@dataclass
class ToolContext:
    weather: WeatherProvider
    session_factory: SessionFactory | None = None
    user_id: uuid.UUID | None = None
    farm_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    allow_save: bool = False
    origin: str = "assistant"
    ledger: WeatherLedger = field(default_factory=WeatherLedger)
    used_engine: bool = False
    used_crop_knowledge: bool = False
    saved_recommendation_ids: list[str] = field(default_factory=list)


class ToolRefusedError(Exception):
    """A tool declined to act. The message goes back to the model."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[Any, ToolContext], Awaitable[BaseModel | dict]]

    def definition(self) -> dict:
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return {"name": self.name, "description": self.description, "input_schema": schema}


@dataclass
class ToolOutcome:
    tool_use_id: str
    name: str
    ok: bool
    content: str
    duration_ms: int
    error_code: str | None = None
    provenance: str | None = None

    def tool_result_block(self) -> dict:
        block = {"type": "tool_result", "tool_use_id": self.tool_use_id, "content": self.content}
        if not self.ok:
            block["is_error"] = True
        return block

    def log_entry(self, tool_input: Any) -> dict:
        return {
            "name": self.name,
            "input": tool_input if isinstance(tool_input, dict) else {},
            "ok": self.ok,
            "duration_ms": self.duration_ms,
            "error_code": self.error_code,
            "provenance": self.provenance,
        }


def _error_content(code: str, message: str, **extra: Any) -> str:
    return json.dumps({"error": code, "message": message, **extra})


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def definitions(self) -> list[dict]:
        # A fixed order keeps the prompt-cache prefix stable between requests.
        return [tool.definition() for tool in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)

    async def execute(
        self, tool_use_id: str, name: str, raw_input: Any, context: ToolContext
    ) -> ToolOutcome:
        started = time.perf_counter()

        def finish(ok: bool, content: str, code: str | None = None, prov: str | None = None):
            outcome = ToolOutcome(
                tool_use_id=tool_use_id,
                name=name,
                ok=ok,
                content=content[:MAX_TOOL_RESULT_CHARS],
                duration_ms=int((time.perf_counter() - started) * 1000),
                error_code=code,
                provenance=prov,
            )
            logger.info(
                "tool=%s ok=%s ms=%s code=%s provenance=%s",
                name,
                ok,
                outcome.duration_ms,
                code,
                prov,
            )
            return outcome

        tool = self._tools.get(name)
        if tool is None:
            return finish(
                False, _error_content("unknown_tool", f"No tool named {name}."), "unknown_tool"
            )

        try:
            arguments = tool.input_model.model_validate(raw_input)
        except ValidationError as exc:
            problems = [
                {"field": ".".join(str(p) for p in e["loc"]), "problem": e["msg"]}
                for e in exc.errors()
            ]
            return finish(
                False,
                _error_content(
                    "invalid_arguments", "The tool arguments failed validation.", problems=problems
                ),
                "invalid_arguments",
            )

        try:
            result = await tool.handler(arguments, context)
        except ToolRefusedError as exc:
            return finish(False, _error_content("refused", str(exc)), "refused")
        except AppError as exc:
            # These messages are written for clients, so they are safe to hand to the model.
            return finish(False, _error_content(exc.code, exc.message), exc.code)
        except Exception:
            logger.exception("tool crashed name=%s", name)
            return finish(
                False, _error_content("tool_failed", "The tool failed unexpectedly."), "tool_failed"
            )

        document = result.model_dump(mode="json") if isinstance(result, BaseModel) else result
        return finish(True, json.dumps(document), prov=_find_provenance(document))


def _find_provenance(document: dict) -> str | None:
    meta = document.get("meta")
    if isinstance(meta, dict):
        return meta.get("provenance")
    return document.get("weather_provenance")
