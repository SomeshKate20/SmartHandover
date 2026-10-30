from fastapi import APIRouter, HTTPException

from ..ai_service import AiServiceError, analyze_notes
from ..schemas import AiMeetingAnalysis, NotesProcessRequest


router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/process-notes", response_model=AiMeetingAnalysis)
async def process_notes(payload: NotesProcessRequest) -> AiMeetingAnalysis:
    try:
        return await analyze_notes(payload)
    except AiServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
