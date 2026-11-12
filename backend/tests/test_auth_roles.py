from sqlalchemy import select

from app.database import SessionLocal
from app.models import User

from .conftest import login, signup


def test_signup_always_gives_user_role(client):
    # trying to sneak in a role should be ignored
    r = client.post("/api/auth/signup", json={
        "name": "Sneaky", "email": "sneaky@test.com", "password": "secret123", "role": "admin",
    })
    assert r.status_code == 201
    assert r.json()["user"]["role"] == "user"


def test_password_is_hashed(client):
    signup(client, "Riya", "riya@test.com", "mypassword")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "riya@test.com"))
        assert user.password_hash != "mypassword"
        assert user.password_hash.startswith("$2")


def test_duplicate_email_rejected(client):
    signup(client, "A", "dup@test.com")
    r = client.post("/api/auth/signup", json={"name": "B", "email": "DUP@test.com", "password": "secret123"})
    assert r.status_code == 409


def test_wrong_password(client):
    r = client.post("/api/auth/login", json={"email": "demo@test.com", "password": "nope"})
    assert r.status_code == 401


def test_no_token_is_401(client):
    assert client.get("/api/tasks").status_code == 401
    assert client.get("/api/admin/users").status_code == 401


def test_normal_user_cannot_call_admin_apis(client, demo_headers):
    assert client.get("/api/admin/users", headers=demo_headers).status_code == 403
    assert client.get("/api/admin/tasks", headers=demo_headers).status_code == 403
    r = client.patch("/api/admin/users/1/role", json={"role": "admin"}, headers=demo_headers)
    assert r.status_code == 403


def test_admin_can_see_everything(client, admin_headers):
    users = client.get("/api/admin/users", headers=admin_headers).json()
    assert {u["email"] for u in users} >= {"admin@test.com", "demo@test.com"}
    tasks = client.get("/api/admin/tasks", headers=admin_headers).json()
    assert len(tasks) == 3  # seeded demo tasks
    assert all(t["owner_email"] == "demo@test.com" for t in tasks)


def test_admin_cannot_change_own_role(client, admin_headers):
    me = client.get("/api/auth/me", headers=admin_headers).json()
    r = client.patch(f"/api/admin/users/{me['id']}/role", json={"role": "user"}, headers=admin_headers)
    assert r.status_code == 400


def test_demoted_admin_loses_access_with_same_token(client, admin_headers):
    headers, new_user = signup(client, "Temp", "temp@test.com")
    client.patch(f"/api/admin/users/{new_user['id']}/role", json={"role": "admin"}, headers=admin_headers)
    assert client.get("/api/admin/users", headers=headers).status_code == 200
    client.patch(f"/api/admin/users/{new_user['id']}/role", json={"role": "user"}, headers=admin_headers)
    # old token still says admin, but the backend checks the DB
    assert client.get("/api/admin/users", headers=headers).status_code == 403


def test_users_only_see_their_own_tasks(client, demo_headers):
    other_headers, _ = signup(client, "Other", "other@test.com")
    demo_tasks = client.get("/api/tasks", headers=demo_headers).json()
    assert len(demo_tasks) == 3
    assert client.get("/api/tasks", headers=other_headers).json() == []

    task_id = demo_tasks[0]["id"]
    assert client.patch(f"/api/tasks/{task_id}", json={"status": "done"}, headers=other_headers).status_code == 404
    assert client.delete(f"/api/tasks/{task_id}", headers=other_headers).status_code == 404


def test_swagger_form_login(client):
    r = client.post("/api/auth/token", data={"username": "demo@test.com", "password": "demopass"})
    assert r.status_code == 200
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=headers).json()["email"] == "demo@test.com"
    assert login(client, "demo@test.com", "demopass")
