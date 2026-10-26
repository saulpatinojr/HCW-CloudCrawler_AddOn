"""The error envelope `{error: {code, message, details?}}`; message is visitor-safe, details carry codes and counts."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers or {}

    def body(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            error["details"] = self.details
        return {"error": error}


DEFAULT_CODES = {
    400: "invalid_request",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    408: "request_timeout",
    413: "too_large",
    415: "unsupported_media_type",
    422: "invalid_request",
    429: "rate_limited",
    500: "internal_error",
    503: "overloaded",
}
DEFAULT_MESSAGES = {
    400: "The request could not be understood.",
    403: "The request was refused.",
    404: "Not found.",
    405: "That method is not allowed here.",
    408: "The upload took too long to arrive.",
    413: "The upload is larger than the limit.",
    415: "Send application/json.",
    422: "The input could not be processed.",
    429: "Too many requests from this client; try again later.",
    500: "Something went wrong on our side.",
    503: "The service is busy; try again shortly.",
}
