import os
import tempfile

# has to happen before the app is imported, settings are read at import time
_db_file = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file}"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["LLM_API_KEY"] = ""
os.environ["ADMIN_EMAIL"] = "admin@test.com"
os.environ["ADMIN_PASSWORD"] = "adminpass"
os.environ["DEMO_USER_EMAIL"] = "demo@test.com"
os.environ["DEMO_USER_PASSWORD"] = "demopass"

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agent.llm import get_llm_client
from app.database import Base, SessionLocal, engine
from app.main import app
from app.seed import seed


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed(db)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def signup(client, name, email, password="secret123"):
    r = client.post("/api/auth/signup", json={"name": name, "email": email, "password": password})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["user"]


@pytest.fixture()
def admin_headers(client):
    return login(client, "admin@test.com", "adminpass")


@pytest.fixture()
def demo_headers(client):
    return login(client, "demo@test.com", "demopass")


# ---------- fake LLM ----------

def tool_call(call_id, name, args):
    return SimpleNamespace(id=call_id, type="function",
                           function=SimpleNamespace(name=name, arguments=json.dumps(args)))


def llm_reply(content=None, tool_calls=None):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class FakeLLM:
    """Plays back a fixed list of responses and remembers what it was sent."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


@pytest.fixture()
def use_fake_llm():
    def _install(responses):
        fake = FakeLLM(responses)
        app.dependency_overrides[get_llm_client] = lambda: fake
        return fake
    return _install
