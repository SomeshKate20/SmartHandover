import json
import logging
import os
import re

import httpx
from pydantic import ValidationError

from .schemas import AiMeetingAnalysis, NotesProcessRequest


logger = logging.getLogger(__name__)
GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"


class AiServiceError(Exception):
    def __init__(self, message: str, status_code: int):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _provider_error_details(response: httpx.Response) -> tuple[str | None, str | None]:
    try:
        body = response.json()
    except ValueError:
        return None, None

    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return None, None

    def safe_code(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        sanitized = re.sub(r"[^A-Za-z0-9_.-]", "_", value)[:80]
        return sanitized or None

    return safe_code(error.get("code")), safe_code(error.get("type"))


def _provider_failure_message(status_code: int, error_code: str | None) -> str:
    if status_code == 401 or error_code == "invalid_api_key":
        return "AI provider authentication failed. Check GROQ_API_KEY in Render."
    if error_code in {"insufficient_quota", "billing_hard_limit_reached"}:
        return "AI provider quota is exhausted. Check the provider account's billing and usage."
    if status_code == 429 or error_code == "rate_limit_exceeded":
        return "AI provider rate limit reached. Please retry shortly."
    if status_code == 403:
        return "AI provider access was denied. Check API key permissions and model access."
    if status_code == 404 or error_code == "model_not_found":
        return "The configured AI model is unavailable. Check GROQ_MODEL and model access."
    if status_code >= 500:
        return "AI provider is temporarily unavailable. Please retry shortly."
    return "AI provider rejected the analysis request. Check the provider error in server logs."


def _extract_output(response: dict) -> str:
    choices = response.get("choices") if isinstance(response, dict) else None
    if isinstance(choices, list) and choices:
        choice = choices[0]
        if isinstance(choice, dict):
            message = choice.get("message")
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]

    logger.error(
        "Groq response did not contain chat completion content",
        extra={
            "exception_class": AiServiceError.__name__,
            "provider_http_status": 200,
            "provider_error_code": None,
        },
    )
    raise AiServiceError("AI provider returned no analysis content.", 502)


async def analyze_notes(payload: NotesProcessRequest) -> AiMeetingAnalysis:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        logger.error("AI analysis unavailable: GROQ_API_KEY is not configured")
        raise AiServiceError("AI analysis is unavailable: configure GROQ_API_KEY on the backend.", 503)

    meeting_context = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
    instructions = """Analyze only the supplied meeting context. Return facts explicitly supported by the notes.
Never invent an owner, deadline, decision, or blocker. Use null for unknown action-item owner/due_date/blocker.
Return concise JSON matching the supplied schema; decisions and blockers must be empty lists when absent."""
    instructions += "\nRequired JSON schema:\n" + json.dumps(AiMeetingAnalysis.model_json_schema())
    request_body = {
        "model": os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip() or DEFAULT_GROQ_MODEL,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": meeting_context},
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.post(
                GROQ_CHAT_COMPLETIONS_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=request_body,
            )
        if response.status_code >= 400:
            error_code, error_type = _provider_error_details(response)
            provider_error = httpx.HTTPStatusError(
                "AI provider returned an error response.",
                request=response.request,
                response=response,
            )
            logger.warning(
                "AI provider request failed",
                extra={
                    "exception_class": type(provider_error).__name__,
                    "provider_http_status": response.status_code,
                    "provider_error_code": error_code,
                    "provider_error_type": error_type,
                },
            )
            raise AiServiceError(
                _provider_failure_message(response.status_code, error_code),
                502,
            ) from provider_error
        raw_output = _extract_output(response.json())
        return AiMeetingAnalysis.model_validate_json(raw_output)
    except httpx.TimeoutException as exc:
        logger.warning(
            "AI provider request timed out",
            extra={
                "exception_class": type(exc).__name__,
                "provider_http_status": None,
                "provider_error_code": None,
            },
        )
        raise AiServiceError("AI analysis timed out. Please try again.", 504) from exc
    except httpx.HTTPError as exc:
        logger.error(
            "AI provider transport failed",
            extra={
                "exception_class": type(exc).__name__,
                "provider_http_status": None,
                "provider_error_code": None,
            },
        )
        raise AiServiceError("AI provider is currently unavailable.", 502) from exc
    except (ValueError, ValidationError) as exc:
        logger.error(
            "AI provider returned invalid structured analysis",
            extra={
                "exception_class": type(exc).__name__,
                "provider_http_status": response.status_code,
                "provider_error_code": None,
            },
        )
        raise AiServiceError("AI provider returned an invalid structured analysis.", 502) from exc
