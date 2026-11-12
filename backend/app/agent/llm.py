from openai import OpenAI

from ..config import settings

_client: OpenAI | None = None


def get_llm_client() -> OpenAI | None:
    """Returns None when no key is set, the agent turns that into a friendly error."""
    global _client
    if not settings.LLM_API_KEY:
        return None
    if _client is None:
        _client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            timeout=settings.LLM_TIMEOUT,
            max_retries=1,
        )
    return _client
