import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function Navbar() {
  const { user, isAdmin, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <header className="navbar">
      <div className="navbar-inner">
        <NavLink to="/" className="brand">
          <img src="/favicon.svg" alt="" width="24" height="24" />
          TaskPilot
        </NavLink>

        {user && (
          <nav className="nav-links">
            <NavLink to="/" end>Chat</NavLink>
            <NavLink to="/tasks">My tasks</NavLink>
            {isAdmin && <NavLink to="/admin">Admin</NavLink>}
          </nav>
        )}

        {user && (
          <div className="nav-user">
            <span className="nav-name">{user.name}</span>
            <span className={`badge badge-${user.role}`}>{user.role}</span>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => {
                logout();
                navigate("/login");
              }}
            >
              Log out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
