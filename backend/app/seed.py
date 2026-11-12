"""Creates the demo admin and demo user on startup (only if they don't exist yet)."""

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import Task, User
from .security import hash_password

log = logging.getLogger("taskpilot.seed")


def _ensure_user(db: Session, email: str, password: str, name: str, role: str) -> User | None:
    if not email or not password:
        return None
    email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user:
        return None
    user = User(name=name, email=email, password_hash=hash_password(password), role=role)
    db.add(user)
    db.flush()
    log.info("created %s account %s", role, email)
    return user


def seed(db: Session) -> None:
    _ensure_user(db, settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD, "Admin", "admin")
    demo = _ensure_user(db, settings.DEMO_USER_EMAIL, settings.DEMO_USER_PASSWORD, "Demo User", "user")

    if demo:
        # a few starter tasks so the agent has something to work with on first login
        today = date.today()
        db.add_all([
            Task(title="Submit monthly report", due_date=today + timedelta(days=2), priority="high", owner_id=demo.id),
            Task(title="Book train tickets for home", due_date=today + timedelta(days=5), priority="medium", owner_id=demo.id),
            Task(title="Read chapter 4 of the ML notes", priority="low", owner_id=demo.id),
        ])
    db.commit()
