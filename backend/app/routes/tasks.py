from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import AuthenticatedUser, get_current_user
from ..models import Meeting, MeetingTask, Task, TaskHistory
from ..schemas import CarryForwardRequest, TaskCreate, TaskHistoryResponse, TaskResponse, TaskStatus, TaskStatusUpdate, TaskUpdate


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def get_task_or_404(task_id: int, db: Session) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def validate_origin_meeting(meeting_id: int | None, db: Session) -> None:
    if meeting_id is not None and db.get(Meeting, meeting_id) is None:
        raise HTTPException(status_code=422, detail="Origin meeting not found")


def record_history(db: Session, task_id: int, event_type: str, details: str) -> None:
    db.add(TaskHistory(task_id=task_id, event_type=event_type, details=details))


@router.get("", response_model=list[TaskResponse])
def list_tasks(
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> list[Task]:
    statement = select(Task).order_by(Task.due_date.asc().nulls_last(), Task.id.desc())
    if status_filter is not None:
        statement = statement.where(Task.status == status_filter)
    return list(db.scalars(statement).all())


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> Task:
    validate_origin_meeting(payload.origin_meeting_id, db)
    task = Task(**payload.model_dump())
    task.title = task.title.strip()
    if task.owner:
        task.owner = task.owner.strip() or None
    db.add(task)
    db.flush()
    record_history(db, task.id, "task_created", "Task created")
    if task.owner:
        record_history(db, task.id, "owner_assigned", f"Owner assigned: {task.owner}")
    if task.origin_meeting_id:
        db.add(MeetingTask(meeting_id=task.origin_meeting_id, task_id=task.id))
    db.commit()
    db.refresh(task)
    return task


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: Session = Depends(get_db)) -> Task:
    return get_task_or_404(task_id, db)


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)) -> Task:
    task = get_task_or_404(task_id, db)
    changes = payload.model_dump(exclude_unset=True)
    if "origin_meeting_id" in changes:
        validate_origin_meeting(changes["origin_meeting_id"], db)
    previous_owner = task.owner
    for field, value in changes.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(task, field, value)
    if "owner" in changes and task.owner != previous_owner:
        record_history(db, task.id, "owner_assigned" if not previous_owner else "owner_changed", f"Owner changed from {previous_owner or 'unassigned'} to {task.owner or 'unassigned'}")
    if "completion_note" in changes and task.completion_note:
        record_history(db, task.id, "completion_outcome_recorded", "Completion outcome recorded")
    db.commit()
    db.refresh(task)
    return task


@router.patch("/{task_id}/status", response_model=TaskResponse)
def update_task_status(
    task_id: int,
    payload: TaskStatusUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Task:
    task = get_task_or_404(task_id, db)
    if task.assignee_clerk_id != user.clerk_id:
        raise HTTPException(status_code=403, detail="Only the assigned user can update this task's status")

    previous_status = task.status
    task.status = payload.status
    if task.status != previous_status:
        record_history(db, task.id, "status_changed", f"Status changed from {previous_status} to {task.status}")
    db.commit()
    db.refresh(task)
    return task


@router.post("/{task_id}/claim", response_model=TaskResponse)
def claim_task(
    task_id: int,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Task:
    task = get_task_or_404(task_id, db)
    if task.assignee_clerk_id is not None and task.assignee_clerk_id != user.clerk_id:
        raise HTTPException(status_code=409, detail="Task is already assigned")
    if task.assignee_clerk_id is None:
        result = db.execute(
            update(Task)
            .where(Task.id == task_id, Task.assignee_clerk_id.is_(None))
            .values(assignee_clerk_id=user.clerk_id)
        )
        if result.rowcount:
            record_history(db, task.id, "task_claimed", "Task assigned to an authenticated user")
            db.commit()
        else:
            db.rollback()
            task = get_task_or_404(task_id, db)
            if task.assignee_clerk_id != user.clerk_id:
                raise HTTPException(status_code=409, detail="Task is already assigned")
        db.refresh(task)
    return task


@router.get("/{task_id}/history", response_model=list[TaskHistoryResponse])
def task_history(task_id: int, db: Session = Depends(get_db)) -> list[TaskHistory]:
    get_task_or_404(task_id, db)
    return list(db.scalars(select(TaskHistory).where(TaskHistory.task_id == task_id).order_by(TaskHistory.created_at.desc(), TaskHistory.id.desc())).all())


@router.post("/{task_id}/carry-forward", response_model=TaskResponse)
def carry_forward(task_id: int, payload: CarryForwardRequest, db: Session = Depends(get_db)) -> Task:
    task = get_task_or_404(task_id, db)
    if task.status == "Completed":
        raise HTTPException(status_code=422, detail="Completed tasks cannot be carried forward")
    if db.get(Meeting, payload.meeting_id) is None:
        raise HTTPException(status_code=404, detail="Target meeting not found")
    existing = db.scalar(select(MeetingTask).where(MeetingTask.task_id == task_id, MeetingTask.meeting_id == payload.meeting_id))
    if existing:
        raise HTTPException(status_code=409, detail="Task is already associated with this meeting")
    db.add(MeetingTask(task_id=task_id, meeting_id=payload.meeting_id))
    record_history(db, task.id, "task_carried_forward", f"Carried forward to meeting #{payload.meeting_id}")
    db.commit()
    db.refresh(task)
    return task
