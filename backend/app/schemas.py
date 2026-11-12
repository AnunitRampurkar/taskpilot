from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Priority = Literal["low", "medium", "high"]
Status = Literal["pending", "done"]


# ---------- auth / users ----------

class SignupIn(BaseModel):
    # no role field on purpose. anything extra in the body is just ignored
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: str
    created_at: datetime


class AdminUserOut(UserOut):
    total_tasks: int = 0
    open_tasks: int = 0


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class RoleUpdate(BaseModel):
    role: Literal["user", "admin"]


# ---------- tasks ----------

class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    due_date: date | None = None
    priority: Priority = "medium"


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    due_date: date | None = None
    priority: Priority | None = None
    status: Status | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    notes: str | None
    due_date: date | None
    priority: str
    status: str
    owner_id: int
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class AdminTaskOut(TaskOut):
    owner_name: str
    owner_email: str


# ---------- chat / agent ----------

class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ToolCallOut(BaseModel):
    name: str
    args: dict[str, Any]
    ok: bool
    summary: str


class PendingActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    summary: str
    created_at: datetime


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    tool_calls: list[ToolCallOut] | None = None
    created_at: datetime


class ChatOut(BaseModel):
    message: ChatMessageOut
    pending_actions: list[PendingActionOut] = []


class ConfirmIn(BaseModel):
    approve: bool
