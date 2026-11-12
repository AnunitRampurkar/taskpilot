import os

from dotenv import load_dotenv

load_dotenv()


def _split(value: str) -> list[str]:
    return [v.strip().rstrip("/") for v in value.split(",") if v.strip()]


class Settings:
    # falls back to a local sqlite file so the app runs without any setup.
    # on Render this should always point to Neon / Postgres
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./taskpilot_dev.db")

    JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret-change-me")
    JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

    # any OpenAI compatible endpoint works, Groq is the default
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30"))
    AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "6"))

    FRONTEND_ORIGINS = _split(os.getenv("FRONTEND_ORIGINS", "http://localhost:5173"))
    APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Kolkata")

    # demo accounts get created on startup if these are set
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
    DEMO_USER_EMAIL = os.getenv("DEMO_USER_EMAIL", "")
    DEMO_USER_PASSWORD = os.getenv("DEMO_USER_PASSWORD", "")


settings = Settings()
