# TaskPilot

**Project B** of the QuantumApps AI Engineer (Full Stack) take-home, Round 1.

TaskPilot is a to-do app where you don't have to click around much. You just type things like *"add a task to submit the monthly report by Friday"* or *"mark the report done and add one to start the next"* and an AI agent picks the right tools, changes the tasks in the database and tells you what it did. There are two roles: users manage only their own tasks, and admins can see every user and every task.

## Live links and demo logins

| | |
|---|---|
| Frontend | https://taskpilot-henna-theta.vercel.app |
| Backend | https://taskpilot-api-2rlg.onrender.com (Swagger docs at https://taskpilot-api-2rlg.onrender.com/docs) |

| Role | Email | Password |
|---|---|---|
| Admin | `admin@taskpilot.dev` | `Admin@123` |
| User | `user@taskpilot.dev` | `User@123` |

The demo user already has 3 tasks in it so you can start chatting straight away. You can also sign up with your own email, it will get the normal user role.

> **Heads up:** the backend is on Render's free plan, so it sleeps after 15 min of no traffic. The first request after that takes around a minute. The frontend shows a yellow "waking up the server" bar while this happens, so please give it a moment.

## Tech stack and why I picked it

| Part | What I used | Why |
|---|---|---|
| Backend | FastAPI, SQLAlchemy 2.0, Pydantic v2 | FastAPI was fixed. SQLAlchemy lets the same code run on SQLite locally and Postgres in prod. |
| LLM | Groq, `llama-3.3-70b-versatile` | Free, really fast, and it supports tool calling properly. I call it through the `openai` Python SDK pointed at Groq's OpenAI compatible URL, so switching to OpenRouter, Gemini etc. is only an env change. |
| Agent | Plain Python loop, no framework | The loop is about 60 lines (`backend/app/agent/runner.py`). I looked at LangGraph, but for 4 to 6 tools a framework felt like extra stuff to explain without adding much. Writing it myself also meant I fully control where the user id comes from. |
| Database | Neon Postgres (free tier) | Render's disk gets wiped on restart and Render Postgres expires in 30 days, so Neon made more sense. |
| Auth | Own JWT auth (PyJWT + bcrypt) | Small enough to write myself and I wanted to see exactly how the role checks work instead of hiding them in a third party service. |
| Frontend | React 18 + Vite + React Router, plain CSS | Simple, builds fast, deploys on Vercel as a static site. No UI library because the app has only 5 screens. |
| Hosting | Vercel (frontend), Render (backend), Neon (DB) | All free, no card needed. |
| Tests | pytest with a fake LLM | So the agent and RBAC logic can be tested without burning API calls. |

## How the AI part works

When a message comes in, the backend builds a prompt with a system message, the last 10 chat messages and the new message. The system prompt also contains today's date and a small 15 day calendar (like `Fri 2026-11-13`). I added that because the model was not reliable at working out "next Friday" on its own, and with the calendar in front of it the dates come out right.

The model gets these tools:

| Tool | Who gets it | What it does |
|---|---|---|
| `add_task` | everyone | create a task (title, due date, priority, notes) |
| `list_tasks` | everyone | list/filter by status, keyword, due date range, priority |
| `update_task` | everyone | change fields, mark done or reopen |
| `delete_tasks` | everyone | asks for confirmation, doesn't delete directly (see below) |
| `list_users` | admin only | see all users with their open task count |
| `assign_task` | admin only | put a task into another user's list |

Then it runs in a loop. The model either answers in text (loop ends) or asks for one or more tool calls. The backend runs each one, sends the results back and calls the model again. This is how multi-step requests work. For *"mark the report done and add a task to start the next one"* the model first calls `list_tasks(search="report")` to find the id, then calls `update_task` and `add_task` in the same turn, and then replies. The loop stops after 6 rounds max so it can't spin forever.

**Safety:** the model never gets to choose whose data it touches. `ToolExecutor` is created with the logged in user from the JWT and every query inside it has `owner_id == current_user.id`. The model only passes task ids, and if it passes someone else's id (prompt injection, hallucination, whatever) the tool just says "no task #12 in this user's list". Admin tools are not even sent to the model for normal users, and they check the role again inside the function anyway. There's a test for this (`test_agent_cannot_touch_other_users_tasks`).

**Errors:** if a tool gets bad input (like `due_date: "next friday"`) the error goes back to the model so it can fix the call itself, which it usually does. If Groq is slow, rate limited or down, the user sees a normal message like *"The AI took too long to answer. Please try again in a moment."* instead of a crash. The whole chat turn runs in one DB transaction, so if the LLM fails halfway nothing gets half applied.

## How login and roles work

* Sign up and log in give back a JWT (HS256, valid 24h). The frontend keeps it in localStorage and sends it as `Authorization: Bearer ...`.
* Passwords are hashed with bcrypt, never stored as plain text.
* The signup schema has no `role` field at all, so every new account is `user`. Even if someone sends `"role": "admin"` in the request it is ignored (there's a test for this too). Only an existing admin can promote someone, from the Admin page, and an admin can't change their own role.
* All `/api/admin/*` routes have a `require_admin` dependency on the whole router. A normal user calling them directly gets **403**, no token gets **401**.
* The role is read from the database on every request, not from the token. So if an admin demotes someone, their old token stops working for admin routes immediately.
* Task routes always filter by the logged in user. Touching someone else's task id gives 404 so it doesn't even reveal that the id exists.
* On the frontend, the Admin link and page only show for admins, and `/admin` redirects normal users. That's just for UX though, the real check is on the backend.

**Trying the RBAC from /docs:** click *Authorize* on the Swagger page, put the email in the `username` field with the password, then try `GET /api/admin/users` with the user account. It returns 403.

## Extra features (beyond the minimum)

1. **Confirmation before delete.** The agent can't delete anything by itself. `delete_tasks` creates a pending action, and the chat shows a Confirm / Cancel card. Ownership is checked again at the moment of confirming.
2. **Shows which tools the agent called.** Every reply has small chips like "✓ List tasks ✓ Update task", and you can expand them to see the exact arguments and results. Failed calls show in red.
3. **Chat history** saved in the DB per user, with a Clear chat button. The last few messages (plus a note of what actions were taken) go back to the model, so follow ups like *"actually make that high priority"* work.
4. **Priorities and due dates**, with overdue dates shown in red.
5. **Admin can assign tasks to other users** through the agent (`assign_task`), and those show an "assigned by admin" tag in the user's list.
6. **Admin can promote/demote users** from the Admin page, and filter all tasks by user and status.
7. **Live task panel** next to the chat that refreshes after each reply, plus a separate My tasks page where you can also add, tick or delete by hand.
8. **Server wake-up banner** for Render's cold start, and friendly messages when the server can't be reached.
9. **Login works from Swagger** (`/api/auth/token`) so the API can be tested without the frontend.
10. **22 backend tests** (pytest) covering auth, RBAC, task ownership, multi-step agent runs, confirmation flow and LLM failures.
11. Works on mobile too (chat and task panel stack).

## Running it locally

You need Python 3.12 and Node 18+.

**Backend**

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then put your Groq key in LLM_API_KEY
uvicorn app.main:app --reload
```

If `DATABASE_URL` is empty it uses a local SQLite file, so you don't need Postgres just to try it. Set `ADMIN_EMAIL` / `ADMIN_PASSWORD` and `DEMO_USER_EMAIL` / `DEMO_USER_PASSWORD` in `.env` and those accounts get created on startup. API docs are at http://localhost:8000/docs.

**Frontend**

```bash
cd frontend
npm install
cp .env.example .env      # VITE_API_URL=http://localhost:8000
npm run dev
```

Open http://localhost:5173.

**Tests**

```bash
cd backend
pytest
```

The tests use a fake LLM that plays back fixed responses, so no API key is needed.

## Deployment notes

* **Neon:** created a free project and copied the connection string into `DATABASE_URL`.
* **Render:** Web Service with root directory `backend`, build `pip install -r requirements.txt`, start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Env vars are the same as `.env.example`. `FRONTEND_ORIGINS` has to be the Vercel URL (no trailing slash) or the browser blocks the requests because of CORS. There is also a `render.yaml` in the repo.
* **Vercel:** root directory `frontend`, framework Vite, env var `VITE_API_URL` = the Render URL. `vercel.json` rewrites every path to `index.html` so refreshing on `/tasks` doesn't give a 404.

## Project structure

```
backend/
  app/
    main.py          app setup, CORS, startup (create tables + seed demo accounts)
    config.py        all env vars in one place
    database.py      engine and session
    models.py        User, Task, ChatMessage, PendingAction
    schemas.py       request/response models
    security.py      bcrypt + JWT
    deps.py          get_current_user, require_admin
    seed.py          demo accounts
    routers/         auth, tasks, chat, admin
    agent/
      tools.py       tool definitions + ToolExecutor (the ownership checks are here)
      runner.py      system prompt and the agent loop
      llm.py         Groq client
  tests/
frontend/
  src/
    api.js           fetch wrapper with error handling
    auth.jsx         login state (context)
    pages/           Login, Signup, Chat, Tasks, Admin
    components/      Navbar, ServerBanner, task tags
```

## What's not finished / what I'd improve

* **No streaming.** The reply comes all at once after the agent finishes its steps. Usually that's 1 to 3 seconds on Groq, but streaming would feel nicer.
* **Free tier limits.** Groq's free tier has rate limits, so if many people test at the same time some requests might get the "busy, try again" message.
* **Token in localStorage.** Fine for a demo, but for real use I'd move to httpOnly cookies with refresh tokens and add rate limiting on login.
* **No migrations.** Tables are made with `create_all` on startup. If the schema changes I'd add Alembic.
* **Only deletes need confirmation.** Bulk updates (like "mark everything done") go through directly. I'd like the agent to ask first when more than 3 tasks change.
* **No reminders.** I'd like to add a daily summary or email reminder for tasks due today, maybe with a Render cron job.
* **No agent evals yet.** The tests check my code with a fake LLM, not the real model's choices. Next step would be a small set of prompts with expected tool calls, run against the real model to compare models and catch prompt regressions.
* **No audit log.** For the kind of public sector work QuantumApps does, I'd log every admin action and agent tool call with who/when.
* No frontend tests yet. I checked the flows by hand in the browser (both roles, desktop and mobile).
