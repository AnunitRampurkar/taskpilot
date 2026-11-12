import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth";
import { DueTag, PriorityTag } from "../components/TaskItem";

const FILTERS = ["all", "pending", "done"];

export default function Tasks() {
  const { request } = useAuth();
  const [tasks, setTasks] = useState([]);
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ title: "", due_date: "", priority: "medium" });

  const load = useCallback(async () => {
    try {
      setTasks(await request(`/api/tasks?status=${filter}`));
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [request, filter]);

  useEffect(() => {
    load();
  }, [load]);

  async function addTask(e) {
    e.preventDefault();
    if (!form.title.trim()) return;
    try {
      await request("/api/tasks", {
        method: "POST",
        body: { title: form.title.trim(), priority: form.priority, due_date: form.due_date || null },
      });
      setForm({ title: "", due_date: "", priority: "medium" });
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function toggle(task) {
    try {
      await request(`/api/tasks/${task.id}`, {
        method: "PATCH",
        body: { status: task.status === "done" ? "pending" : "done" },
      });
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function remove(task) {
    if (!window.confirm(`Delete "${task.title}"?`)) return;
    try {
      await request(`/api/tasks/${task.id}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  const doneCount = tasks.filter((t) => t.status === "done").length;

  return (
    <div className="card">
      <div className="page-header">
        <div>
          <h2>My tasks</h2>
          <p className="muted small">
            Everything the agent does shows up here. You can also edit things by hand.
          </p>
        </div>
        <div className="segmented">
          {FILTERS.map((f) => (
            <button key={f} className={filter === f ? "active" : ""} onClick={() => setFilter(f)}>
              {f}
            </button>
          ))}
        </div>
      </div>

      <form className="quick-add" onSubmit={addTask}>
        <input
          placeholder="Quick add a task"
          value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
          maxLength={200}
        />
        <input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
        <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
        </select>
        <button className="btn btn-primary">Add</button>
      </form>

      {error && <div className="error">{error}</div>}

      {loading ? (
        <p className="muted">Loading...</p>
      ) : tasks.length === 0 ? (
        <p className="muted center pad">No tasks here. Add one above or ask the agent in Chat.</p>
      ) : (
        <>
          {filter === "all" && (
            <p className="small muted">
              {doneCount} of {tasks.length} done
            </p>
          )}
          <ul className="task-list">
            {tasks.map((t) => (
              <li key={t.id} className={t.status === "done" ? "done" : ""}>
                <input
                  type="checkbox"
                  checked={t.status === "done"}
                  onChange={() => toggle(t)}
                  aria-label={`Mark ${t.title} as ${t.status === "done" ? "pending" : "done"}`}
                />
                <div className="task-main">
                  <div className="task-title">
                    {t.title} <span className="muted small">#{t.id}</span>
                  </div>
                  {t.notes && <div className="small muted">{t.notes}</div>}
                  <div className="row gap-sm">
                    <PriorityTag priority={t.priority} />
                    <DueTag date={t.due_date} done={t.status === "done"} />
                    {t.created_by_id && t.created_by_id !== t.owner_id && (
                      <span className="tag tag-assigned">assigned by admin</span>
                    )}
                  </div>
                </div>
                <button className="btn btn-ghost btn-sm" onClick={() => remove(t)} aria-label="Delete task">
                  Delete
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
