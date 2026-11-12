import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth";
import { DueTag, PriorityTag } from "../components/TaskItem";

export default function Admin() {
  const { user: me, request } = useAuth();
  const [tab, setTab] = useState("users");
  const [users, setUsers] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [userFilter, setUserFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [error, setError] = useState("");

  const loadUsers = useCallback(async () => {
    try {
      setUsers(await request("/api/admin/users"));
    } catch (err) {
      setError(err.message);
    }
  }, [request]);

  const loadTasks = useCallback(async () => {
    const params = new URLSearchParams({ status: statusFilter });
    if (userFilter) params.set("user_id", userFilter);
    try {
      setTasks(await request(`/api/admin/tasks?${params}`));
    } catch (err) {
      setError(err.message);
    }
  }, [request, userFilter, statusFilter]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  useEffect(() => {
    if (tab === "tasks") loadTasks();
  }, [tab, loadTasks]);

  async function changeRole(u, role) {
    if (!window.confirm(`Make ${u.name} ${role === "admin" ? "an admin" : "a normal user"}?`)) return;
    try {
      await request(`/api/admin/users/${u.id}/role`, { method: "PATCH", body: { role } });
      loadUsers();
    } catch (err) {
      setError(err.message);
    }
  }

  const totalOpen = users.reduce((n, u) => n + u.open_tasks, 0);

  return (
    <div className="card">
      <div className="page-header">
        <div>
          <h2>Admin</h2>
          <p className="muted small">
            {users.length} users, {totalOpen} open tasks in total
          </p>
        </div>
        <div className="segmented">
          <button className={tab === "users" ? "active" : ""} onClick={() => setTab("users")}>Users</button>
          <button className={tab === "tasks" ? "active" : ""} onClick={() => setTab("tasks")}>All tasks</button>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      {tab === "users" && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Open / total</th>
                <th>Joined</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.name}</td>
                  <td>{u.email}</td>
                  <td><span className={`badge badge-${u.role}`}>{u.role}</span></td>
                  <td>{u.open_tasks} / {u.total_tasks}</td>
                  <td className="small muted">{new Date(u.created_at).toLocaleDateString()}</td>
                  <td>
                    {u.id === me.id ? (
                      <span className="small muted">you</span>
                    ) : u.role === "admin" ? (
                      <button className="btn btn-ghost btn-sm" onClick={() => changeRole(u, "user")}>Make user</button>
                    ) : (
                      <button className="btn btn-ghost btn-sm" onClick={() => changeRole(u, "admin")}>Make admin</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "tasks" && (
        <>
          <div className="row gap-sm filters">
            <select value={userFilter} onChange={(e) => setUserFilter(e.target.value)}>
              <option value="">All users</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>{u.name} ({u.email})</option>
              ))}
            </select>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="all">Any status</option>
              <option value="pending">Pending</option>
              <option value="done">Done</option>
            </select>
          </div>
          {tasks.length === 0 ? (
            <p className="muted center pad">No tasks match.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Task</th>
                    <th>Owner</th>
                    <th>Priority</th>
                    <th>Due</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {tasks.map((t) => (
                    <tr key={t.id} className={t.status === "done" ? "done" : ""}>
                      <td className="muted small">{t.id}</td>
                      <td>{t.title}</td>
                      <td>
                        {t.owner_name}
                        <div className="small muted">{t.owner_email}</div>
                      </td>
                      <td><PriorityTag priority={t.priority} /></td>
                      <td><DueTag date={t.due_date} done={t.status === "done"} /></td>
                      <td><span className={`status status-${t.status}`}>{t.status}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
