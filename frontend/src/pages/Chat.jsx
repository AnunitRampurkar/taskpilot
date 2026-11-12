import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { DueTag, PriorityTag } from "../components/TaskItem";

const EXAMPLES = [
  "Add a task to submit the monthly report by Friday, high priority",
  "What's due this week?",
  "Mark the report task as done and add a task to start the next one",
  "Delete the train tickets task",
];

const TOOL_LABELS = {
  add_task: "Add task",
  list_tasks: "List tasks",
  update_task: "Update task",
  delete_tasks: "Delete",
  list_users: "List users",
  assign_task: "Assign task",
};

// the model sometimes still sends markdown, strip the bold/heading marks so it reads clean
function cleanText(text) {
  return (text || "").replace(/\*\*(.+?)\*\*/g, "$1").replace(/^#+\s*/gm, "");
}

function ToolCalls({ calls }) {
  const [open, setOpen] = useState(false);
  if (!calls || calls.length === 0) return null;
  return (
    <div className="tools">
      <button className="tools-toggle" onClick={() => setOpen(!open)}>
        {open ? "Hide" : "Show"} {calls.length} tool call{calls.length > 1 ? "s" : ""}
      </button>
      <div className="tool-chips">
        {calls.map((c, i) => (
          <span key={i} className={`chip ${c.ok ? "chip-ok" : "chip-fail"}`} title={c.summary}>
            {c.ok ? "✓" : "✕"} {TOOL_LABELS[c.name] || c.name}
          </span>
        ))}
      </div>
      {open && (
        <ul className="tool-details">
          {calls.map((c, i) => (
            <li key={i}>
              <code>{c.name}({JSON.stringify(c.args)})</code>
              <div className={c.ok ? "muted small" : "late small"}>{c.summary}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ConfirmCard({ action, onResolve }) {
  const [busy, setBusy] = useState(false);
  async function resolve(approve) {
    setBusy(true);
    await onResolve(action.id, approve);
    setBusy(false);
  }
  return (
    <div className="confirm-card">
      <div>
        <strong>Confirm needed</strong>
        <div className="small">{action.summary}</div>
      </div>
      <div className="row">
        <button className="btn btn-danger btn-sm" disabled={busy} onClick={() => resolve(true)}>Confirm</button>
        <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => resolve(false)}>Cancel</button>
      </div>
    </div>
  );
}

export default function Chat() {
  const { user, request } = useAuth();
  const [messages, setMessages] = useState([]);
  const [pending, setPending] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const bottomRef = useRef(null);

  const loadTasks = useCallback(async () => {
    try {
      setTasks(await request("/api/tasks?status=pending"));
    } catch {
      // side panel is a nice to have, ignore errors here
    }
  }, [request]);

  useEffect(() => {
    Promise.all([request("/api/chat/history"), request("/api/chat/pending"), loadTasks()])
      .then(([history, pend]) => {
        setMessages(history);
        setPending(pend);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [request, loadTasks]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, pending, sending]);

  async function send(text) {
    const message = text.trim();
    if (!message || sending) return;
    setError("");
    setInput("");
    const tempId = `temp-${Date.now()}`;
    setMessages((m) => [...m, { id: tempId, role: "user", content: message }]);
    setSending(true);
    try {
      const data = await request("/api/chat", { method: "POST", body: { message } });
      setMessages((m) => [...m, data.message]);
      if (data.pending_actions.length) setPending((p) => [...p, ...data.pending_actions]);
      loadTasks();
    } catch (err) {
      // nothing was saved on the server, so drop the optimistic message and give the text back
      setMessages((m) => m.filter((x) => x.id !== tempId));
      setInput(message);
      setError(err.message);
    } finally {
      setSending(false);
    }
  }

  async function resolvePending(id, approve) {
    try {
      const msg = await request(`/api/chat/pending/${id}`, { method: "POST", body: { approve } });
      setMessages((m) => [...m, msg]);
      loadTasks();
    } catch (err) {
      setError(err.message);
    }
    setPending((p) => p.filter((a) => a.id !== id));
  }

  async function clearChat() {
    if (!window.confirm("Clear the chat history? Your tasks stay as they are.")) return;
    try {
      await request("/api/chat/history", { method: "DELETE" });
      setMessages([]);
      setPending([]);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="chat-layout">
      <section className="card chat-card">
        <div className="chat-header">
          <div>
            <h2>Hi {user.name.split(" ")[0]}</h2>
            <p className="muted small">Tell me what to add, change or check. I'll use the tools and tell you what I did.</p>
          </div>
          {messages.length > 0 && (
            <button className="btn btn-ghost btn-sm" onClick={clearChat}>Clear chat</button>
          )}
        </div>

        <div className="messages">
          {loading && <p className="muted center">Loading...</p>}

          {!loading && messages.length === 0 && (
            <div className="empty">
              <p className="muted">Try one of these:</p>
              <div className="examples">
                {EXAMPLES.map((ex) => (
                  <button key={ex} className="example" onClick={() => send(ex)}>{ex}</button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m) => (
            <div key={m.id} className={`msg msg-${m.role}`}>
              <div className="bubble">{cleanText(m.content)}</div>
              {m.role === "assistant" && <ToolCalls calls={m.tool_calls} />}
            </div>
          ))}

          {pending.map((a) => (
            <ConfirmCard key={a.id} action={a} onResolve={resolvePending} />
          ))}

          {sending && (
            <div className="msg msg-assistant">
              <div className="bubble typing"><span /><span /><span /></div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {error && <div className="error chat-error">{error}</div>}

        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="e.g. Remind me to pay the hostel fees by the 15th"
            maxLength={2000}
            disabled={sending}
          />
          <button className="btn btn-primary" disabled={sending || !input.trim()}>Send</button>
        </form>
      </section>

      <aside className="card side-card">
        <div className="side-header">
          <h3>Open tasks</h3>
          <Link to="/tasks" className="small">View all</Link>
        </div>
        {tasks.length === 0 ? (
          <p className="muted small">Nothing pending. Nice.</p>
        ) : (
          <ul className="side-list">
            {tasks.map((t) => (
              <li key={t.id}>
                <div className="side-title">
                  <span className="muted small">#{t.id}</span> {t.title}
                </div>
                <div className="row gap-sm">
                  <PriorityTag priority={t.priority} />
                  <DueTag date={t.due_date} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  );
}
