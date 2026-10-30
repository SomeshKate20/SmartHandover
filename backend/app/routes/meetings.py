import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Meeting
from ..schemas import MeetingCreate, MeetingResponse, MeetingUpdate


router = APIRouter(prefix="/api/meetings", tags=["meetings"])


def meeting_response(meeting: Meeting) -> MeetingResponse:
    return MeetingResponse(
        id=meeting.id,
        title=meeting.title,
        meeting_type=meeting.meeting_type,
        meeting_date=meeting.meeting_date,
        agenda=meeting.agenda,
        participants=meeting.participant_list(),
        raw_notes=meeting.raw_notes,
        summary=meeting.summary,
        decisions=meeting.decisions,
        status=meeting.status,
        created_at=meeting.created_at,
        updated_at=meeting.updated_at,
    )


def get_meeting_or_404(meeting_id: int, db: Session) -> Meeting:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting


@router.get("", response_model=list[MeetingResponse])
def list_meetings(db: Session = Depends(get_db)) -> list[MeetingResponse]:
    meetings = db.scalars(select(Meeting).order_by(Meeting.meeting_date.desc(), Meeting.id.desc())).all()
    return [meeting_response(meeting) for meeting in meetings]


@router.post("", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
def create_meeting(payload: MeetingCreate, db: Session = Depends(get_db)) -> MeetingResponse:
    meeting = Meeting(
        title=payload.title.strip(),
        meeting_type=payload.meeting_type.strip(),
        meeting_date=payload.meeting_date,
        agenda=payload.agenda.strip(),
        participants=json.dumps(payload.participants),
        raw_notes=payload.raw_notes.strip(),
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting_response(meeting)


@router.get("/{meeting_id}", response_model=MeetingResponse)
def get_meeting(meeting_id: int, db: Session = Depends(get_db)) -> MeetingResponse:
    return meeting_response(get_meeting_or_404(meeting_id, db))


@router.patch("/{meeting_id}", response_model=MeetingResponse)
def update_meeting(
    meeting_id: int, payload: MeetingUpdate, db: Session = Depends(get_db)
) -> MeetingResponse:
    meeting = get_meeting_or_404(meeting_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "participants" and value is not None:
            value = json.dumps(value)
        elif isinstance(value, str):
            value = value.strip()
        setattr(meeting, field, value)
    db.commit()
    db.refresh(meeting)
    return meeting_response(meeting)
