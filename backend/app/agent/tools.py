"""
Tools the LLM is allowed to call.

The important bit: the model never decides whose tasks it is working on.
ToolExecutor is created with the logged in user and every query is filtered
by that user's id here in Python. The model only ever sends task ids, and if
an id belongs to someone else it simply looks like it doesn't exist.
"""

import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import PendingAction, Task, User

PRIORITIES = {"low", "medium", "high"}


class ToolError(Exception):
    """Bad input from the model. The message goes back to the model so it can fix the call."""


# ---------- schemas sent to the LLM (OpenAI function calling format) ----------

def _fn(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


DATE_HINT = "Date in YYYY-MM-DD format."

USER_TOOLS = [
    _fn(
        "add_task",
        "Create a new task for the current user.",
        {
            "title": {"type": "string", "description": "Short title of the task."},
            "due_date": {"type": "string", "description": DATE_HINT + " Leave out if no date was given."},
            "priority": {"type": "string", "enum": ["low", "medium", "high"]},
            "notes": {"type": "string", "description": "Optional extra details."},
        },
        ["title"],
    ),
    _fn(
        "list_tasks",
        "List the current user's tasks. Use the filters to narrow it down. "
        "Call this to find a task's id before updating or deleting it.",
        {
            "status": {"type": "string", "enum": ["pending", "done", "all"], "description": "Default is pending."},
            "search": {"type": "string", "description": "Keyword to match in the title or notes."},
            "due_from": {"type": "string", "description": DATE_HINT + " Only tasks due on or after this."},
            "due_to": {"type": "string", "description": DATE_HINT + " Only tasks due on or before this."},
            "priority": {"type": "string", "enum": ["low", "medium", "high"]},
        },
    ),
    _fn(
        "update_task",
        "Change an existing task. Use status='done' to mark it complete or 'pending' to reopen it. "
        "Only pass the fields that should change.",
        {
            "task_id": {"type": "integer"},
            "title": {"type": "string"},
            "due_date": {"type": "string", "description": DATE_HINT + " Use an empty string to clear it."},
            "priority": {"type": "string", "enum": ["low", "medium", "high"]},
            "status": {"type": "string", "enum": ["pending", "done"]},
            "notes": {"type": "string"},
        },
        ["task_id"],
    ),
    _fn(
        "delete_tasks",
        "Ask to delete one or more tasks. Nothing is deleted straight away: the user gets a "
        "Confirm button in the app and the delete only happens if they press it.",
        {
            "task_ids": {"type": "array", "items": {"type": "integer"}},
        },
        ["task_ids"],
    ),
]

ADMIN_TOOLS = [
    _fn(
        "list_users",
        "Admin only. List all users with their email and number of open tasks.",
        {},
    ),
    _fn(
        "assign_task",
        "Admin only. Create a task in another user's list.",
        {
            "user_email": {"type": "string"},
            "title": {"type": "string"},
            "due_date": {"type": "string", "description": DATE_HINT},
            "priority": {"type": "string", "enum": ["low", "medium", "high"]},
            "notes": {"type": "string"},
        },
        ["user_email", "title"],
    ),
]


# ---------- helpers ----------

def _parse_date(value: Any, field: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        raise ToolError(f"{field} must be a date like 2026-11-20, got '{value}'.")


def _parse_priority(value: Any) -> str:
    p = str(value).lower().strip()
    if p not in PRIORITIES:
        raise ToolError("priority must be low, medium or high.")
    return p


def _parse_int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ToolError(f"{field} must be a number.")


def task_to_dict(t: Task) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "priority": t.priority,
        "status": t.status,
        "notes": t.notes,
    }


# ---------- executor ----------

class ToolExecutor:
    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user
        self.pending_actions: list[PendingAction] = []

    @property
    def is_admin(self) -> bool:
        return self.user.role == "admin"

    def specs(self) -> list[dict]:
        return USER_TOOLS + ADMIN_TOOLS if self.is_admin else list(USER_TOOLS)

    def run(self, name: str, raw_args: str | dict | None) -> tuple[dict, dict]:
        """Runs one tool call. Returns (result for the model, log entry for the UI)."""
        args: dict = {}
        try:
            if isinstance(raw_args, dict):
                args = raw_args
            elif raw_args:
                args = json.loads(raw_args)
            if not isinstance(args, dict):
                raise ToolError("Arguments must be a JSON object.")

            handler = getattr(self, f"_tool_{name}", None)
            allowed = {s["function"]["name"] for s in self.specs()}
            if handler is None or name not in allowed:
                raise ToolError(f"Unknown tool '{name}'.")

            result, summary = handler(**args)
            return result, {"name": name, "args": args, "ok": True, "summary": summary}

        except json.JSONDecodeError:
            msg = "Could not read the tool arguments, they were not valid JSON."
        except TypeError as e:
            # model passed an argument the function doesn't take
            msg = f"Wrong arguments for {name}: {e}"
        except ToolError as e:
            msg = str(e)
        return {"error": msg}, {"name": name, "args": args, "ok": False, "summary": msg}

    def _own_task(self, task_id: Any) -> Task:
        tid = _parse_int(task_id, "task_id")
        task = self.db.scalar(select(Task).where(Task.id == tid, Task.owner_id == self.user.id))
        if task is None:
            raise ToolError(f"There is no task #{tid} in this user's list.")
        return task

    # ----- user tools -----

    def _tool_add_task(self, title: str, due_date: str | None = None, priority: str = "medium",
                       notes: str | None = None):
        title = (title or "").strip()
        if not title:
            raise ToolError("title can't be empty.")
        task = Task(
            title=title[:200],
            due_date=_parse_date(due_date, "due_date"),
            priority=_parse_priority(priority or "medium"),
            notes=notes or None,
            owner_id=self.user.id,
        )
        self.db.add(task)
        self.db.flush()
        return {"created": task_to_dict(task)}, f"Added #{task.id} '{task.title}'"

    def _tool_list_tasks(self, status: str = "pending", search: str | None = None,
                         due_from: str | None = None, due_to: str | None = None,
                         priority: str | None = None):
        q = select(Task).where(Task.owner_id == self.user.id)
        status = (status or "pending").lower()
        if status in ("pending", "done"):
            q = q.where(Task.status == status)
        if search:
            like = f"%{search.strip().lower()}%"
            q = q.where(func.lower(Task.title).like(like) | func.lower(func.coalesce(Task.notes, "")).like(like))
        d_from = _parse_date(due_from, "due_from")
        d_to = _parse_date(due_to, "due_to")
        if d_from:
            q = q.where(Task.due_date >= d_from)
        if d_to:
            q = q.where(Task.due_date <= d_to)
        if priority:
            q = q.where(Task.priority == _parse_priority(priority))

        q = q.order_by(Task.due_date.is_(None), Task.due_date, Task.id).limit(50)
        tasks = self.db.scalars(q).all()
        return {"count": len(tasks), "tasks": [task_to_dict(t) for t in tasks]}, f"Found {len(tasks)} task(s)"

    def _tool_update_task(self, task_id: int, title: str | None = None, due_date: str | None = None,
                          priority: str | None = None, status: str | None = None,
                          notes: str | None = None):
        task = self._own_task(task_id)
        changes = []
        if title is not None and title.strip():
            task.title = title.strip()[:200]
            changes.append("title")
        if due_date is not None:
            task.due_date = _parse_date(due_date, "due_date")
            changes.append("due date")
        if priority is not None:
            task.priority = _parse_priority(priority)
            changes.append("priority")
        if notes is not None:
            task.notes = notes or None
            changes.append("notes")
        if status is not None:
            status = status.lower()
            if status not in ("pending", "done"):
                raise ToolError("status must be pending or done.")
            task.status = status
            task.completed_at = datetime.now(timezone.utc) if status == "done" else None
            changes.append(f"status -> {status}")
        if not changes:
            raise ToolError("Nothing to update, pass at least one field to change.")
        self.db.flush()
        return {"updated": task_to_dict(task)}, f"Updated #{task.id} ({', '.join(changes)})"

    def _tool_delete_tasks(self, task_ids: list):
        if not isinstance(task_ids, list) or not task_ids:
            raise ToolError("task_ids must be a non empty list of ids.")
        tasks = [self._own_task(tid) for tid in dict.fromkeys(task_ids)]
        titles = ", ".join(f"'{t.title}'" for t in tasks)
        label = "task" if len(tasks) == 1 else f"{len(tasks)} tasks"
        pending = PendingAction(
            user_id=self.user.id,
            action="delete_tasks",
            payload={"task_ids": [t.id for t in tasks]},
            summary=f"Delete {label}: {titles}",
        )
        self.db.add(pending)
        self.db.flush()
        self.pending_actions.append(pending)
        return (
            {
                "status": "waiting_for_user_confirmation",
                "message": "Not deleted yet. The user has to press Confirm in the app.",
                "tasks": [task_to_dict(t) for t in tasks],
            },
            f"Asked to confirm deleting {label}",
        )

    # ----- admin tools -----

    def _require_admin(self):
        # double check even though the tool isn't offered to normal users
        if not self.is_admin:
            raise ToolError("Only admins can do this.")

    def _tool_list_users(self):
        self._require_admin()
        open_count = (
            select(Task.owner_id, func.count(Task.id).label("n"))
            .where(Task.status == "pending")
            .group_by(Task.owner_id)
            .subquery()
        )
        rows = self.db.execute(
            select(User, func.coalesce(open_count.c.n, 0))
            .outerjoin(open_count, open_count.c.owner_id == User.id)
            .order_by(User.id)
        ).all()
        users = [
            {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "open_tasks": n}
            for u, n in rows
        ]
        return {"users": users}, f"Listed {len(users)} user(s)"

    def _tool_assign_task(self, user_email: str, title: str, due_date: str | None = None,
                          priority: str = "medium", notes: str | None = None):
        self._require_admin()
        email = (user_email or "").strip().lower()
        target = self.db.scalar(select(User).where(User.email == email))
        if target is None:
            raise ToolError(f"No user with email {user_email}.")
        if not (title or "").strip():
            raise ToolError("title can't be empty.")
        task = Task(
            title=title.strip()[:200],
            due_date=_parse_date(due_date, "due_date"),
            priority=_parse_priority(priority or "medium"),
            notes=notes or None,
            owner_id=target.id,
            created_by_id=self.user.id,
        )
        self.db.add(task)
        self.db.flush()
        return (
            {"created": task_to_dict(task), "assigned_to": target.email},
            f"Assigned #{task.id} '{task.title}' to {target.email}",
        )
