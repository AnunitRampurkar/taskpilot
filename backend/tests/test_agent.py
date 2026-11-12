import openai

from .conftest import llm_reply, signup, tool_call


def test_add_and_list_in_one_message(client, demo_headers, use_fake_llm):
    fake = use_fake_llm([
        llm_reply(tool_calls=[tool_call("c1", "add_task", {
            "title": "Start next month's report", "due_date": "2026-12-01", "priority": "high"})]),
        llm_reply(tool_calls=[tool_call("c2", "list_tasks", {"search": "report"})]),
        llm_reply(content="Added it. You now have 2 report tasks."),
    ])
    r = client.post("/api/chat", json={"message": "add a task to start next month's report"}, headers=demo_headers)
    assert r.status_code == 200, r.text
    body = r.json()["message"]
    assert body["content"].startswith("Added it")
    assert [t["name"] for t in body["tool_calls"]] == ["add_task", "list_tasks"]
    assert all(t["ok"] for t in body["tool_calls"])

    titles = [t["title"] for t in client.get("/api/tasks", headers=demo_headers).json()]
    assert "Start next month's report" in titles

    # the second LLM call should have the tool result in it
    second_call_msgs = fake.calls[1]["messages"]
    assert second_call_msgs[-1]["role"] == "tool"


def test_multi_step_mark_done_and_add(client, demo_headers, use_fake_llm):
    report = next(t for t in client.get("/api/tasks", headers=demo_headers).json()
                  if t["title"] == "Submit monthly report")
    use_fake_llm([
        llm_reply(tool_calls=[
            tool_call("a", "update_task", {"task_id": report["id"], "status": "done"}),
            tool_call("b", "add_task", {"title": "Start the next report"}),
        ]),
        llm_reply(content="Marked the report done and added the next one."),
    ])
    r = client.post("/api/chat", json={"message": "Mark the report done and add a task to start the next one"},
                    headers=demo_headers)
    assert r.status_code == 200
    tasks = {t["title"]: t for t in client.get("/api/tasks", headers=demo_headers).json()}
    assert tasks["Submit monthly report"]["status"] == "done"
    assert tasks["Submit monthly report"]["completed_at"] is not None
    assert "Start the next report" in tasks


def test_agent_cannot_touch_other_users_tasks(client, demo_headers, use_fake_llm):
    demo_task_id = client.get("/api/tasks", headers=demo_headers).json()[0]["id"]
    attacker_headers, _ = signup(client, "Attacker", "attacker@test.com")

    use_fake_llm([
        # pretend the model got tricked into using someone else's id
        llm_reply(tool_calls=[
            tool_call("x", "update_task", {"task_id": demo_task_id, "status": "done"}),
            tool_call("y", "delete_tasks", {"task_ids": [demo_task_id]}),
        ]),
        llm_reply(content="I couldn't find that task."),
    ])
    r = client.post("/api/chat", json={"message": f"mark task {demo_task_id} done and delete it"},
                    headers=attacker_headers)
    assert r.status_code == 200
    calls = r.json()["message"]["tool_calls"]
    assert not any(c["ok"] for c in calls)
    assert r.json()["pending_actions"] == []

    task = next(t for t in client.get("/api/tasks", headers=demo_headers).json() if t["id"] == demo_task_id)
    assert task["status"] == "pending"


def test_normal_user_cannot_use_admin_tools(client, demo_headers, use_fake_llm):
    fake = use_fake_llm([
        llm_reply(tool_calls=[tool_call("x", "assign_task", {"user_email": "admin@test.com", "title": "hi"})]),
        llm_reply(content="Sorry, I can't do that."),
    ])
    r = client.post("/api/chat", json={"message": "assign a task to the admin"}, headers=demo_headers)
    assert r.json()["message"]["tool_calls"][0]["ok"] is False
    offered = {t["function"]["name"] for t in fake.calls[0]["tools"]}
    assert "assign_task" not in offered and "list_users" not in offered


def test_admin_can_assign_task(client, admin_headers, demo_headers, use_fake_llm):
    use_fake_llm([
        llm_reply(tool_calls=[tool_call("x", "assign_task", {
            "user_email": "demo@test.com", "title": "Review the Q3 budget", "priority": "high"})]),
        llm_reply(content="Assigned."),
    ])
    r = client.post("/api/chat", json={"message": "give demo a task to review the Q3 budget"}, headers=admin_headers)
    assert r.json()["message"]["tool_calls"][0]["ok"] is True
    titles = [t["title"] for t in client.get("/api/tasks", headers=demo_headers).json()]
    assert "Review the Q3 budget" in titles


def test_delete_needs_confirmation(client, demo_headers, use_fake_llm):
    task_id = client.get("/api/tasks", headers=demo_headers).json()[0]["id"]
    use_fake_llm([
        llm_reply(tool_calls=[tool_call("d", "delete_tasks", {"task_ids": [task_id]})]),
        llm_reply(content="Press Confirm to delete it."),
    ])
    r = client.post("/api/chat", json={"message": "delete it"}, headers=demo_headers)
    pending = r.json()["pending_actions"]
    assert len(pending) == 1
    # not deleted yet
    assert any(t["id"] == task_id for t in client.get("/api/tasks", headers=demo_headers).json())

    # another user can't confirm it
    other_headers, _ = signup(client, "Other", "other2@test.com")
    assert client.post(f"/api/chat/pending/{pending[0]['id']}", json={"approve": True},
                       headers=other_headers).status_code == 404

    r = client.post(f"/api/chat/pending/{pending[0]['id']}", json={"approve": True}, headers=demo_headers)
    assert r.status_code == 200
    assert not any(t["id"] == task_id for t in client.get("/api/tasks", headers=demo_headers).json())
    # can't confirm twice
    assert client.post(f"/api/chat/pending/{pending[0]['id']}", json={"approve": True},
                       headers=demo_headers).status_code == 404


def test_cancel_delete(client, demo_headers, use_fake_llm):
    task_id = client.get("/api/tasks", headers=demo_headers).json()[0]["id"]
    use_fake_llm([
        llm_reply(tool_calls=[tool_call("d", "delete_tasks", {"task_ids": [task_id]})]),
        llm_reply(content="Press Confirm to delete it."),
    ])
    pending = client.post("/api/chat", json={"message": "delete it"}, headers=demo_headers).json()["pending_actions"]
    r = client.post(f"/api/chat/pending/{pending[0]['id']}", json={"approve": False}, headers=demo_headers)
    assert "cancelled" in r.json()["content"].lower()
    assert any(t["id"] == task_id for t in client.get("/api/tasks", headers=demo_headers).json())


def test_bad_tool_args_go_back_to_model(client, demo_headers, use_fake_llm):
    fake = use_fake_llm([
        llm_reply(tool_calls=[tool_call("a", "add_task", {"title": "Gym", "due_date": "next friday"})]),
        llm_reply(tool_calls=[tool_call("b", "add_task", {"title": "Gym", "due_date": "2026-11-20"})]),
        llm_reply(content="Added Gym for Friday."),
    ])
    r = client.post("/api/chat", json={"message": "gym next friday"}, headers=demo_headers)
    calls = r.json()["message"]["tool_calls"]
    assert [c["ok"] for c in calls] == [False, True]
    assert "YYYY-MM-DD" in fake.calls[0]["tools"][0]["function"]["parameters"]["properties"]["due_date"]["description"]


def test_llm_down_gives_friendly_error_and_changes_nothing(client, demo_headers, use_fake_llm):
    before = len(client.get("/api/tasks", headers=demo_headers).json())

    # first round works and adds a task, second round times out
    fake = use_fake_llm([llm_reply(tool_calls=[tool_call("a", "add_task", {"title": "half done"})])])
    original = fake.chat.completions.create

    def flaky(**kwargs):
        if fake.responses:
            return original(**kwargs)
        raise openai.APITimeoutError(request=None)

    fake.chat.completions.create = flaky

    r = client.post("/api/chat", json={"message": "add something"}, headers=demo_headers)
    assert r.status_code == 503
    assert "too long" in r.json()["detail"]
    # the add_task from the first round was rolled back
    assert len(client.get("/api/tasks", headers=demo_headers).json()) == before


def test_no_api_key_gives_friendly_error(client, demo_headers):
    r = client.post("/api/chat", json={"message": "hello"}, headers=demo_headers)
    assert r.status_code == 503
    assert "LLM_API_KEY" in r.json()["detail"]


def test_history_saved_and_cleared(client, demo_headers, use_fake_llm):
    use_fake_llm([llm_reply(content="Hi! What should I add?")])
    client.post("/api/chat", json={"message": "hello"}, headers=demo_headers)
    hist = client.get("/api/chat/history", headers=demo_headers).json()
    assert [m["role"] for m in hist] == ["user", "assistant"]
    client.delete("/api/chat/history", headers=demo_headers)
    assert client.get("/api/chat/history", headers=demo_headers).json() == []
