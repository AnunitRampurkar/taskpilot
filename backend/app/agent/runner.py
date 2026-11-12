"""
The agent loop.

1. build the prompt (system prompt + last few chat messages + new message)
2. ask the model, giving it the tool list
3. if it asks for tools, run them and send the results back, then go to 2
4. stop when it answers in plain text (or after AGENT_MAX_STEPS rounds)

Everything happens in one DB transaction. If the LLM call fails halfway
we roll back, so the user never ends up with half of a request applied.
"""

import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import openai
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import ChatMessage, User
from .tools import ToolExecutor

log = logging.getLogger("taskpilot.agent")

HISTORY_LIMIT = 10


class AgentError(Exception):
    """Something went wrong talking to the LLM. The message is safe to show the user."""


SYSTEM_PROMPT = """You are TaskPilot, a to-do assistant inside a web app. You help {name} manage their tasks by calling the tools you have.

Today is {today_long}. Use this calendar to turn words like "Friday" or "next Monday" into dates:
{calendar}

Rules:
- Always use tools to read or change tasks. Never say you added, changed or deleted something unless a tool result confirms it.
- To change or delete an existing task you need its id. If you don't know it, call list_tasks first, using the search filter with a keyword from the user's message (set status to "all" if the task might already be done).
- If one message asks for several things, do all of them. Use one tool call per action.
- Send dates to tools as YYYY-MM-DD. "This week" means from today until Sunday {sunday}.
- delete_tasks does not delete anything by itself. The user must press Confirm in the app, so tell them that.
- If a search matches more than one task and it is not clear which one the user means, ask them instead of guessing.
- If a tool returns an error, either fix your call and try again or explain the problem simply.
- Keep replies short and friendly. Say what you did. When listing tasks use bullet points with the due date and priority.
- You can only see and change this user's own tasks.{admin_note}"""

ADMIN_NOTE = """
- This user is an admin. They can also use list_users and assign_task to put a task in someone else's list."""


def _today():
    try:
        return datetime.now(ZoneInfo(settings.APP_TIMEZONE)).date()
    except Exception:
        return datetime.now().date()


def build_system_prompt(user: User) -> str:
    today = _today()
    days = [today + timedelta(days=i) for i in range(15)]
    calendar = "\n".join(
        f"- {d.strftime('%a')} {d.isoformat()}" + (" (today)" if i == 0 else "")
        for i, d in enumerate(days)
    )
    sunday = today + timedelta(days=6 - today.weekday())
    return SYSTEM_PROMPT.format(
        name=user.name,
        today_long=today.strftime("%A, %d %B %Y"),
        calendar=calendar,
        sunday=sunday.isoformat(),
        admin_note=ADMIN_NOTE if user.role == "admin" else "",
    )


def _history(db: Session, user: User) -> list[dict]:
    rows = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.id.desc())
        .limit(HISTORY_LIMIT)
    ).all()
    messages = []
    for m in reversed(rows):
        content = m.content
        # remind the model what it did last time, mostly so it remembers task ids
        # when the user says something like "actually make that high priority"
        if m.role == "assistant" and m.tool_calls:
            done = "; ".join(t["summary"] for t in m.tool_calls if t.get("ok"))
            if done:
                content += f"\n\n[actions taken: {done}]"
        messages.append({"role": m.role, "content": content})
    return messages


def _call_llm(client, messages: list[dict], tools: list[dict]):
    try:
        return client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.1,
        )
    except openai.APITimeoutError:
        raise AgentError("The AI took too long to answer. Please try again in a moment.")
    except openai.RateLimitError:
        raise AgentError("The free AI tier is getting a lot of requests right now. Please wait a few seconds and try again.")
    except openai.APIConnectionError:
        raise AgentError("Couldn't reach the AI service. Please try again in a moment.")
    except openai.AuthenticationError:
        log.error("LLM auth failed, check LLM_API_KEY")
        raise AgentError("The AI service is not set up correctly on the server.")
    except openai.BadRequestError as e:
        # Groq returns 400 'tool_use_failed' when the model writes a broken tool call.
        # the caller retries once before giving up
        log.warning("LLM bad request: %s", e)
        raise
    except openai.APIError as e:
        log.exception("LLM error")
        raise AgentError("The AI service had a problem. Please try again.") from e


def run_agent(db: Session, user: User, message: str, client) -> tuple[ChatMessage, list]:
    if client is None:
        raise AgentError("The AI service isn't configured on the server yet (LLM_API_KEY is missing).")

    executor = ToolExecutor(db, user)
    tools = executor.specs()
    messages = [{"role": "system", "content": build_system_prompt(user)}]
    messages += _history(db, user)
    messages.append({"role": "user", "content": message})

    tool_log: list[dict] = []
    reply = None

    try:
        for _ in range(settings.AGENT_MAX_STEPS):
            try:
                response = _call_llm(client, messages, tools)
            except openai.BadRequestError:
                try:
                    response = _call_llm(client, messages, tools)
                except openai.BadRequestError:
                    raise AgentError("The AI got confused by that request. Could you try rephrasing it?")

            msg = response.choices[0].message
            if not msg.tool_calls:
                reply = (msg.content or "").strip()
                break

            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            })
            for tc in msg.tool_calls:
                result, entry = executor.run(tc.function.name, tc.function.arguments)
                tool_log.append(entry)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str),
                })

        if reply is None:
            reply = "I did a few steps but couldn't finish that one. Have a look at your task list and tell me what's still missing."
        if not reply:
            reply = "Done." if tool_log else "Sorry, I didn't get that. Could you say it another way?"

        db.add(ChatMessage(user_id=user.id, role="user", content=message))
        assistant_msg = ChatMessage(
            user_id=user.id, role="assistant", content=reply, tool_calls=tool_log or None
        )
        db.add(assistant_msg)
        db.commit()
        db.refresh(assistant_msg)
        for p in executor.pending_actions:
            db.refresh(p)
        return assistant_msg, executor.pending_actions

    except Exception:
        db.rollback()
        raise
