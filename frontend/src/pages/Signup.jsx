import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function Signup() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    if (form.password.length < 6) {
      setError("Password needs at least 6 characters.");
      return;
    }
    setBusy(true);
    try {
      await signup(form.name, form.email, form.password);
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-card card">
      <h1>Create account</h1>
      <p className="muted">New accounts start with the normal user role.</p>
      <form onSubmit={onSubmit} className="form">
        <label>
          Name
          <input value={form.name} onChange={set("name")} required maxLength={80} autoFocus />
        </label>
        <label>
          Email
          <input type="email" value={form.email} onChange={set("email")} required />
        </label>
        <label>
          Password
          <input type="password" value={form.password} onChange={set("password")} required minLength={6} maxLength={72} />
        </label>
        {error && <div className="error">{error}</div>}
        <button className="btn btn-primary" disabled={busy}>
          {busy ? "Creating..." : "Sign up"}
        </button>
      </form>
      <p className="small muted center">
        Already have an account? <Link to="/login">Log in</Link>
      </p>
    </div>
  );
}
