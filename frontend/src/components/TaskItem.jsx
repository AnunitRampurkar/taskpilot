export function formatDue(dateStr) {
  if (!dateStr) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const due = new Date(dateStr + "T00:00:00");
  const diff = Math.round((due - today) / 86400000);
  const pretty = due.toLocaleDateString(undefined, { day: "numeric", month: "short" });
  if (diff === 0) return { text: "Today", late: false };
  if (diff === 1) return { text: "Tomorrow", late: false };
  if (diff < 0) return { text: `${pretty} (overdue)`, late: true };
  if (diff < 7) return { text: due.toLocaleDateString(undefined, { weekday: "short" }) + `, ${pretty}`, late: false };
  return { text: pretty, late: false };
}

export function PriorityTag({ priority }) {
  return <span className={`tag tag-${priority}`}>{priority}</span>;
}

export function DueTag({ date, done }) {
  const due = formatDue(date);
  if (!due) return <span className="muted small">No due date</span>;
  return <span className={`small ${due.late && !done ? "late" : "muted"}`}>{due.text}</span>;
}
