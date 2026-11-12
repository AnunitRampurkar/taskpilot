"""Plain REST endpoints for the task list page. Everything is scoped to the logged in user."""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Task, User
from ..schemas import TaskCreate, TaskOut, TaskUpdate

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _get_own(db: Session, user: User, task_id: int) -> Task:
    task = db.scalar(select(Task).where(Task.id == task_id, Task.owner_id == user.id))
    if task is None:
        # 404 and not 403 so we don't even leak that the id exists
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


@router.get("", response_model=list[TaskOut])
def list_my_tasks(
    status: Literal["pending", "done", "all"] = Query("all"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = select(Task).where(Task.owner_id == user.id)
    if status != "all":
        q = q.where(Task.status == status)
    q = q.order_by(Task.status.desc(), Task.due_date.is_(None), Task.due_date, Task.id)
    return db.scalars(q).all()


@router.post("", response_model=TaskOut, status_code=201)
def create_task(data: TaskCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = Task(**data.model_dump(), owner_id=user.id)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: int, data: TaskUpdate, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    task = _get_own(db, user, task_id)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(task, field, value)
    if "status" in changes:
        task.completed_at = datetime.now(timezone.utc) if task.status == "done" else None
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = _get_own(db, user, task_id)
    db.delete(task)
    db.commit()
    return Response(status_code=204)
