from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Task, User
from ..schemas import AdminTaskOut, AdminUserOut, RoleUpdate, TaskOut, UserOut

# require_admin on the whole router, so every route here is blocked for normal users
router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/users", response_model=list[AdminUserOut])
def list_users(db: Session = Depends(get_db)):
    total = func.count(Task.id)
    open_ = func.sum(case((Task.status == "pending", 1), else_=0))
    rows = db.execute(
        select(User, total, open_).outerjoin(Task, Task.owner_id == User.id).group_by(User.id).order_by(User.id)
    ).all()
    return [
        AdminUserOut(**UserOut.model_validate(u).model_dump(), total_tasks=t or 0, open_tasks=o or 0)
        for u, t, o in rows
    ]


@router.patch("/users/{user_id}/role", response_model=UserOut)
def change_role(user_id: int, data: RoleUpdate, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    if user_id == admin.id:
        # stops the last admin from locking everyone out by accident
        raise HTTPException(status_code=400, detail="You can't change your own role.")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    user.role = data.role
    db.commit()
    db.refresh(user)
    return user


@router.get("/tasks", response_model=list[AdminTaskOut])
def list_all_tasks(
    user_id: int | None = Query(None),
    status: str = Query("all", pattern="^(all|pending|done)$"),
    db: Session = Depends(get_db),
):
    q = select(Task, User).join(User, Task.owner_id == User.id)
    if user_id is not None:
        q = q.where(Task.owner_id == user_id)
    if status != "all":
        q = q.where(Task.status == status)
    q = q.order_by(Task.status.desc(), Task.due_date.is_(None), Task.due_date, Task.id)
    return [
        AdminTaskOut(**TaskOut.model_validate(t).model_dump(), owner_name=u.name, owner_email=u.email)
        for t, u in db.execute(q).all()
    ]
