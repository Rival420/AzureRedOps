import { Outlet, Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function Layout() {
  const { username, logout } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const active = (p: string) =>
    p === "/" ? loc.pathname === "/" : loc.pathname.startsWith(p);

  return (
    <div className="app-shell">
      <div className="topbar">
        <div className="row" style={{ gap: 26 }}>
          <Link to="/" className="brand">
            <span className="dot" />
            AzureRedOps <small>console</small>
          </Link>
          <Link
            to="/"
            className="muted"
            style={active("/") ? { color: "var(--text)" } : undefined}
          >
            Assessments
          </Link>
          <Link
            to="/reference"
            className="muted"
            style={active("/reference") ? { color: "var(--text)" } : undefined}
          >
            Reference
          </Link>
        </div>
        <div className="row" style={{ gap: 16 }}>
          <span className="tac-meta">
            link <b>secure</b>
          </span>
          <span className="muted mono" style={{ fontSize: 12 }}>
            {username ? `op:${username}` : ""}
          </span>
          <button
            className="btn-ghost btn-sm"
            onClick={() => {
              logout();
              nav("/login");
            }}
          >
            Logout
          </button>
        </div>
      </div>
      <div className="container">
        <Outlet />
      </div>
    </div>
  );
}
