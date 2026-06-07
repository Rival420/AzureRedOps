import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(username, password);
      nav("/");
    } catch {
      setError("Invalid username or password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <div
          className="brand"
          style={{ marginBottom: 6, fontSize: 20 }}
        >
          <span className="dot" /> AzureRedOps <small>console</small>
        </div>
        <p
          className="tac-meta"
          style={{ marginBottom: 22 }}
        >
          tactical access terminal <span className="cursor" />
        </p>
        {error && <div className="error-banner">{error}</div>}
        <div className="field">
          <label>Operator ID</label>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
          />
        </div>
        <div className="field">
          <label>Passphrase</label>
          <input
            type="password"
            placeholder="••••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <button className="btn-primary" style={{ width: "100%" }} disabled={busy}>
          {busy ? "Authenticating…" : "Establish Session"}
        </button>
        <p className="notice" style={{ marginTop: 18 }}>
          Authorized, educational security testing only. All operations are
          logged.
        </p>
      </form>
    </div>
  );
}
