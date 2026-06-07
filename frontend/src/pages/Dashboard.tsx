import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Assessment } from "../api/types";

export default function Dashboard() {
  const [items, setItems] = useState<Assessment[]>([]);
  const [view, setView] = useState<"active" | "archived">("active");
  const [showCreate, setShowCreate] = useState(false);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    const data = await api.get<Assessment[]>(`/assessments?status=${view}`);
    setItems(data);
    setLoading(false);
  }
  useEffect(() => {
    load();
  }, [view]);

  return (
    <div>
      <div className="row between" style={{ marginBottom: 18 }}>
        <div>
          <h1 className="page-title">Assessments</h1>
          <div className="muted">Engagements and their archived history.</div>
        </div>
        <button className="btn-primary" onClick={() => setShowCreate(true)}>
          + New assessment
        </button>
      </div>

      <div className="tabs">
        <div className={`tab ${view === "active" ? "active" : ""}`} onClick={() => setView("active")}>
          Active
        </div>
        <div className={`tab ${view === "archived" ? "active" : ""}`} onClick={() => setView("archived")}>
          Archived
        </div>
      </div>

      {loading ? (
        <div className="empty">Loading…</div>
      ) : items.length === 0 ? (
        <div className="empty">No {view} assessments yet.</div>
      ) : (
        <div className="grid cols-2">
          {items.map((a) => (
            <Link key={a.id} to={`/assessments/${a.id}`} className="card" style={{ color: "inherit" }}>
              <div className="row between">
                <strong style={{ fontSize: 16 }}>{a.name}</strong>
                <span className={`badge ${a.status}`}>{a.status}</span>
              </div>
              {a.client && <div className="muted" style={{ marginTop: 4 }}>{a.client}</div>}
              {a.description && (
                <div style={{ marginTop: 8, fontSize: 13 }}>{a.description}</div>
              )}
              <div className="row" style={{ marginTop: 12, gap: 18 }}>
                <span className="muted mono">{a.token_count} tokens</span>
                <span className="muted mono">{a.job_count} jobs</span>
              </div>
            </Link>
          ))}
        </div>
      )}

      {showCreate && <CreateModal onClose={() => setShowCreate(false)} onCreated={load} />}
    </div>
  );
}

function CreateModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [client, setClient] = useState("");
  const [description, setDescription] = useState("");
  const [scope_notes, setScope] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    await api.post("/assessments", { name, client, description, scope_notes });
    setBusy(false);
    onCreated();
    onClose();
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <form className="card modal" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h2 style={{ marginTop: 0 }}>New assessment</h2>
        <div className="field">
          <label>Name *</label>
          <input value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
        </div>
        <div className="field">
          <label>Client / Org</label>
          <input value={client} onChange={(e) => setClient(e.target.value)} />
        </div>
        <div className="field">
          <label>Description</label>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <div className="field">
          <label>Scope / Rules of engagement</label>
          <textarea value={scope_notes} onChange={(e) => setScope(e.target.value)} />
        </div>
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={busy || !name}>Create</button>
        </div>
      </form>
    </div>
  );
}
