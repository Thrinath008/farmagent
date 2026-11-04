"""Application errors and the centralized handlers that turn them into safe JSON."""

import logging
import uuid

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("farmagent.errors")


class AppError(Exception):
    """An error whose code and message are safe to show to API clients."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "internal_error"
    message = "Something went wrong on the server."

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "The requested item does not exist."


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"
    message = "A valid guest session is required."


class BadRequestError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_request"
    message = "The request could not be processed."


class WeatherError(AppError):
    """Base class for weather failures. Never falls back to simulated data."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "weather_unavailable"
    message = "Live weather could not be retrieved right now."


class WeatherNotConfiguredError(WeatherError):
    code = "weather_not_configured"
    message = "Live weather is not configured on this server (OPENWEATHER_API_KEY is missing)."


class WeatherAuthError(WeatherError):
    code = "weather_auth_failed"
    message = "The weather provider rejected the configured API key."


class WeatherRateLimitedError(WeatherError):
    code = "weather_rate_limited"
    message = "The weather provider's request limit has been reached. Try again shortly."


class WeatherDataInvalidError(WeatherError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "weather_data_invalid"
    message = "The weather provider returned data that failed validation, so it was not used."


class LocationNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "location_not_found"
    message = "That location could not be found."


class AgentError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "agent_unavailable"
    message = "The AI assistant is unavailable right now. Your other tools still work."


class AgentNotConfiguredError(AgentError):
    code = "agent_not_configured"
    message = "The AI assistant is not configured on this server (ANTHROPIC_API_KEY is missing)."


class AgentTimeoutError(AgentError):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    code = "agent_timeout"
    message = "The AI assistant took too long to respond. Try again."


def error_body(code: str, message: str, request_id: str | None, **extra: object) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id, **extra}}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or uuid.uuid4().hex


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, _request_id(request)),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Field paths and messages only: the rejected input is never echoed back.
        fields = [
            {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=jsonable_encoder(
                error_body(
                    "validation_error",
                    "Some of the submitted values are not valid.",
                    _request_id(request),
                    fields=fields,
                )
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body("http_error", message, _request_id(request)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(SQLAlchemyError)
    async def _database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        request_id = _request_id(request)
        logger.error("database error request_id=%s type=%s", request_id, type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=error_body(
                "database_unavailable",
                "Saved farm data is unavailable right now. Try again shortly.",
                request_id,
            ),
        )
