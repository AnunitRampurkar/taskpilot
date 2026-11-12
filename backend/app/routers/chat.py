from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..agent.llm import get_llm_client
from ..agent.runner import AgentError, run_agent
from ..database import get_db
from ..deps import get_current_user
from ..models import ChatMessage, PendingAction, Task, User
from ..schemas import ChatIn, ChatMessageOut, ChatOut, ConfirmIn, PendingActionOut

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatOut)
def chat(
    data: ChatIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    llm=Depends(get_llm_client),
):
    try:
        message, pending = run_agent(db, user, data.message.strip(), llm)
    except AgentError as e:
        # 503 with a readable message, the frontend shows it inside the chat
        raise HTTPException(status_code=503, detail=str(e))
    return ChatOut(message=message, pending_actions=pending)


@router.get("/history", response_model=list[ChatMessageOut])
def history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(ChatMessage).where(ChatMessage.user_id == user.id).order_by(ChatMessage.id.desc()).limit(50)
    ).all()
    return list(reversed(rows))


@router.delete("/history", status_code=204)
def clear_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(delete(ChatMessage).where(ChatMessage.user_id == user.id))
    db.execute(
        delete(PendingAction).where(PendingAction.user_id == user.id, PendingAction.status == "pending")
    )
    db.commit()
    return Response(status_code=204)


@router.get("/pending", response_model=list[PendingActionOut])
def list_pending(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(PendingAction)
        .where(PendingAction.user_id == user.id, PendingAction.status == "pending")
        .order_by(PendingAction.id)
    ).all()


@router.post("/pending/{action_id}", response_model=ChatMessageOut)
def resolve_pending(action_id: int, data: ConfirmIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    action = db.scalar(
        select(PendingAction).where(PendingAction.id == action_id, PendingAction.user_id == user.id)
    )
    if action is None or action.status != "pending":
        raise HTTPException(status_code=404, detail="This request was already handled or doesn't exist.")

    if not data.approve:
        action.status = "cancelled"
        text = "Okay, cancelled. Nothing was deleted."
        log = [{"name": "delete_tasks", "args": action.payload, "ok": True, "summary": "Cancelled by user"}]
    else:
        ids = action.payload.get("task_ids", [])
        # check ownership again at the moment of deleting, not just when it was proposed
        tasks = db.scalars(select(Task).where(Task.id.in_(ids), Task.owner_id == user.id)).all()
        for t in tasks:
            db.delete(t)
        action.status = "approved"
        if tasks:
            names = ", ".join(f"'{t.title}'" for t in tasks)
            text = f"Deleted {names}."
        else:
            text = "Those tasks were already gone, so nothing to delete."
        log = [{"name": "delete_tasks", "args": action.payload, "ok": True,
                "summary": f"Deleted {len(tasks)} task(s) after confirmation"}]

    msg = ChatMessage(user_id=user.id, role="assistant", content=text, tool_calls=log)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg
