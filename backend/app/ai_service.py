import json
import os

import httpx
from pydantic import ValidationError

from .schemas import AiMeetingAnalysis, NotesProcessRequest


class AiServiceError(Exception):
    def __init__(self, message: str, status_code: int):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _extract_output(response: dict) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    for output in response.get("output", []):
        for content in output.get("content", []):
            if isinstance(content.get("text"), str):
                return content["text"]
    raise AiServiceError("AI provider returned no analysis content.", 502)


async def analyze_notes(payload: NotesProcessRequest) -> AiMeetingAnalysis:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise AiServiceError("AI analysis is unavailable: configure OPENAI_API_KEY on the backend.", 503)

    meeting_context = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
    instructions = """Analyze only the supplied meeting context. Return facts explicitly supported by the notes.
Never invent an owner, deadline, decision, or blocker. Use null for unknown action-item owner/due_date/blocker.
Return concise JSON matching the supplied schema; decisions and blockers must be empty lists when absent."""
    request_body = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "instructions": instructions,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": meeting_context}]}],
        "text": {"format": {"type": "json_schema", "name": "meeting_analysis", "strict": True, "schema": AiMeetingAnalysis.model_json_schema()}},
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=request_body,
            )
        if response.status_code >= 400:
            raise AiServiceError("AI provider could not complete the analysis.", 502)
        raw_output = _extract_output(response.json())
        return AiMeetingAnalysis.model_validate_json(raw_output)
    except httpx.TimeoutException as exc:
        raise AiServiceError("AI analysis timed out. Please try again.", 504) from exc
    except httpx.HTTPError as exc:
        raise AiServiceError("AI provider is currently unavailable.", 502) from exc
    except (json.JSONDecodeError, ValidationError) as exc:
        raise AiServiceError("AI provider returned an invalid structured analysis.", 502) from exc
