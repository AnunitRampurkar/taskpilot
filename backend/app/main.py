import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .database import Base, SessionLocal, engine
from .routers import admin, auth, chat, tasks
from .seed import seed

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("taskpilot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # small app, so create_all is enough. would switch to alembic if the schema starts changing
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed(db)
    if settings.JWT_SECRET.startswith("dev-only"):
        log.warning("JWT_SECRET is not set, using the dev default. Set it in production!")
    yield


app = FastAPI(
    title="TaskPilot API",
    description="Backend for TaskPilot, a to-do app you control by chatting with an AI agent.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on our side. Please try again."})


app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(chat.router)
app.include_router(admin.router)


@app.get("/", tags=["health"])
def root():
    return {"app": "TaskPilot", "docs": "/docs"}


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
