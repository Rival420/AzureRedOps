import { Outlet, Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function Layout() {
  const { username, logout } = useAuth();
  const nav = useNavigate();
  return (
    <div className="app-shell">
      <div className="topbar">
        <div className="row" style={{ gap: 24 }}>
          <Link to="/" className="brand">
            <span className="dot" />
            AzureRedOps <small>console</small>
          </Link>
          <Link to="/" className="muted">Assessments</Link>
          <Link to="/reference" className="muted">Reference</Link>
        </div>
        <div className="row">
          <span className="muted mono">{username}</span>
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
