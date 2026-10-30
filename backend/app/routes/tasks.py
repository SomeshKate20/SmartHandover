from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Meeting, Task
from ..schemas import TaskCreate, TaskResponse, TaskStatus, TaskUpdate


router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def get_task_or_404(task_id: int, db: Session) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def validate_origin_meeting(meeting_id: int | None, db: Session) -> None:
    if meeting_id is not None and db.get(Meeting, meeting_id) is None:
        raise HTTPException(status_code=422, detail="Origin meeting not found")


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
    for field, value in changes.items():
        if isinstance(value, str):
            value = value.strip() or None
        setattr(task, field, value)
    db.commit()
    db.refresh(task)
    return task
