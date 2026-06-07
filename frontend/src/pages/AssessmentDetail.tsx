import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Assessment, CatalogGroup, Operation, Job, VaultToken } from "../api/types";
import { OperationForm } from "../components/OperationForm";
import { JobConsole } from "../components/JobConsole";

type Tab = "operations" | "jobs" | "tokens" | "info";

export default function AssessmentDetail() {
  const { id } = useParams();
  const assessmentId = Number(id);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [tab, setTab] = useState<Tab>("operations");

  async function loadAssessment() {
    setAssessment(await api.get<Assessment>(`/assessments/${assessmentId}`));
  }
  useEffect(() => {
    loadAssessment();
  }, [assessmentId]);

  if (!assessment) return <div className="empty">Loading…</div>;

  return (
    <div>
      <div className="row between" style={{ marginBottom: 4 }}>
        <h1 className="page-title">{assessment.name}</h1>
        <span className={`badge ${assessment.status}`}>{assessment.status}</span>
      </div>
      <div className="muted" style={{ marginBottom: 18 }}>
        {assessment.client || "—"}
      </div>

      <div className="tabs">
        {(["operations", "jobs", "tokens", "info"] as Tab[]).map((t) => (
          <div key={t} className={`tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>
            {t[0].toUpperCase() + t.slice(1)}
          </div>
        ))}
      </div>

      {tab === "operations" && <OperationsTab assessmentId={assessmentId} />}
      {tab === "jobs" && <JobsTab assessmentId={assessmentId} />}
      {tab === "tokens" && <TokensTab assessmentId={assessmentId} />}
      {tab === "info" && <InfoTab assessment={assessment} onChange={loadAssessment} />}
    </div>
  );
}

/* ---------------- Operations ---------------- */
function OperationsTab({ assessmentId }: { assessmentId: number }) {
  const [catalog, setCatalog] = useState<CatalogGroup[]>([]);
  const [selected, setSelected] = useState<Operation | null>(null);
  const [activeJob, setActiveJob] = useState<number | null>(null);

  useEffect(() => {
    api.get<CatalogGroup[]>("/catalog").then(setCatalog);
  }, []);

  return (
    <div className="grid" style={{ gridTemplateColumns: "280px 1fr", alignItems: "start" }}>
      <div className="card" style={{ padding: 10 }}>
        {catalog.map((g) => (
          <div key={g.key} style={{ marginBottom: 12 }}>
            <div className="muted" style={{ fontSize: 11, textTransform: "uppercase", padding: "4px 8px" }}>
              {g.title}
            </div>
            {g.operations.map((op) => (
              <div
                key={op.activity}
                className="tab"
                style={{
                  display: "block",
                  borderBottom: "none",
                  borderLeft: selected?.activity === op.activity ? "2px solid var(--accent)" : "2px solid transparent",
                  color: selected?.activity === op.activity ? "var(--text)" : "var(--muted)",
                  padding: "6px 10px",
                }}
                onClick={() => {
                  setSelected(op);
                  setActiveJob(null);
                }}
              >
                {op.name}
              </div>
            ))}
          </div>
        ))}
      </div>

      <div className="card">
        {!selected ? (
          <div className="empty">Select an operation from the left.</div>
        ) : (
          <>
            <h2 style={{ marginTop: 0 }}>{selected.name}</h2>
            <OperationForm
              assessmentId={assessmentId}
              op={selected}
              onLaunched={(jobId) => setActiveJob(jobId)}
            />
            {activeJob && (
              <div style={{ marginTop: 20, borderTop: "1px solid var(--border)", paddingTop: 16 }}>
                <JobConsole jobId={activeJob} />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/* ---------------- Jobs ---------------- */
function JobsTab({ assessmentId }: { assessmentId: number }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [open, setOpen] = useState<number | null>(null);

  async function load() {
    setJobs(await api.get<Job[]>(`/assessments/${assessmentId}/jobs`));
  }
  useEffect(() => {
    load();
  }, [assessmentId]);

  return (
    <div className="grid" style={{ gap: 16 }}>
      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Operation</th>
              <th>Activity</th>
              <th>Status</th>
              <th>Created</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td className="mono">{j.id}</td>
                <td>{j.label}</td>
                <td className="mono">{j.activity}</td>
                <td><span className={`badge ${j.status}`}>{j.status}</span></td>
                <td className="muted mono">{j.created_at.replace("T", " ").slice(0, 19)}</td>
                <td>
                  <button className="btn-sm" onClick={() => setOpen(open === j.id ? null : j.id)}>
                    {open === j.id ? "Hide" : "View"}
                  </button>
                </td>
              </tr>
            ))}
            {jobs.length === 0 && (
              <tr><td colSpan={6} className="empty">No jobs run yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {open && (
        <div className="card">
          <JobConsole jobId={open} onDone={load} />
        </div>
      )}
    </div>
  );
}

/* ---------------- Tokens (vault) ---------------- */
function TokensTab({ assessmentId }: { assessmentId: number }) {
  const [tokens, setTokens] = useState<VaultToken[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [reveal, setReveal] = useState<{ access_token: string; refresh_token: string | null; claims: Record<string, unknown> } | null>(null);

  async function load() {
    setTokens(await api.get<VaultToken[]>(`/assessments/${assessmentId}/tokens`));
  }
  useEffect(() => {
    load();
  }, [assessmentId]);

  async function doReveal(tid: number) {
    setReveal(await api.get(`/assessments/${assessmentId}/tokens/${tid}/reveal`));
  }
  async function remove(tid: number) {
    if (!confirm("Delete this token?")) return;
    await api.del(`/assessments/${assessmentId}/tokens/${tid}`);
    load();
  }

  return (
    <div className="grid" style={{ gap: 16 }}>
      <div className="row between">
        <div className="muted">Encrypted at rest. Stored access/refresh tokens for this engagement.</div>
        <button className="btn-primary btn-sm" onClick={() => setShowAdd(true)}>+ Add token</button>
      </div>
      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead>
            <tr><th>Name</th><th>User</th><th>Tenant</th><th>Expires</th><th></th></tr>
          </thead>
          <tbody>
            {tokens.map((t) => (
              <tr key={t.id}>
                <td>{t.name}</td>
                <td className="mono">{t.username || "—"}</td>
                <td className="mono">{t.tenant_id || "—"}</td>
                <td>
                  {t.expires_human ? (
                    <span className={`badge ${t.is_expired ? "failed" : "success"}`}>
                      {t.is_expired ? "expired" : t.expires_human}
                    </span>
                  ) : "—"}
                </td>
                <td className="row" style={{ gap: 6 }}>
                  <button className="btn-sm" onClick={() => doReveal(t.id)}>Reveal</button>
                  <button className="btn-sm btn-danger" onClick={() => remove(t.id)}>Delete</button>
                </td>
              </tr>
            ))}
            {tokens.length === 0 && (
              <tr><td colSpan={5} className="empty">No tokens stored.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {reveal && (
        <div className="modal-overlay" onClick={() => setReveal(null)}>
          <div className="card modal" onClick={(e) => e.stopPropagation()} style={{ width: 640 }}>
            <h2 style={{ marginTop: 0 }}>Token</h2>
            <label>Access token</label>
            <div className="json-view" style={{ whiteSpace: "pre-wrap", maxHeight: 120 }}>{reveal.access_token}</div>
            {reveal.refresh_token && (
              <>
                <label style={{ marginTop: 10 }}>Refresh token</label>
                <div className="json-view" style={{ whiteSpace: "pre-wrap", maxHeight: 100 }}>{reveal.refresh_token}</div>
              </>
            )}
            <label style={{ marginTop: 10 }}>Claims</label>
            <div className="json-view">{JSON.stringify(reveal.claims, null, 2)}</div>
            <div className="row" style={{ justifyContent: "flex-end", marginTop: 12 }}>
              <button onClick={() => setReveal(null)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {showAdd && <AddTokenModal assessmentId={assessmentId} onClose={() => setShowAdd(false)} onAdded={load} />}
    </div>
  );
}

function AddTokenModal({ assessmentId, onClose, onAdded }: { assessmentId: number; onClose: () => void; onAdded: () => void }) {
  const [name, setName] = useState("");
  const [access_token, setAccess] = useState("");
  const [refresh_token, setRefresh] = useState("");
  const [tenant_id, setTenant] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    await api.post(`/assessments/${assessmentId}/tokens`, {
      name, access_token, refresh_token: refresh_token || undefined, tenant_id: tenant_id || undefined,
    });
    setBusy(false);
    onAdded();
    onClose();
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <form className="card modal" onClick={(e) => e.stopPropagation()} onSubmit={submit} style={{ width: 560 }}>
        <h2 style={{ marginTop: 0 }}>Add token</h2>
        <div className="field"><label>Name *</label>
          <input value={name} onChange={(e) => setName(e.target.value)} required /></div>
        <div className="field"><label>Access token *</label>
          <textarea value={access_token} onChange={(e) => setAccess(e.target.value)} required /></div>
        <div className="field"><label>Refresh token</label>
          <textarea value={refresh_token} onChange={(e) => setRefresh(e.target.value)} /></div>
        <div className="field"><label>Tenant (override)</label>
          <input value={tenant_id} onChange={(e) => setTenant(e.target.value)} /></div>
        <div className="row" style={{ justifyContent: "flex-end" }}>
          <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn-primary" disabled={busy || !name || !access_token}>Save</button>
        </div>
      </form>
    </div>
  );
}

/* ---------------- Info ---------------- */
function InfoTab({ assessment, onChange }: { assessment: Assessment; onChange: () => void }) {
  const nav = useNavigate();
  const [form, setForm] = useState({
    name: assessment.name,
    client: assessment.client || "",
    description: assessment.description || "",
    scope_notes: assessment.scope_notes || "",
  });
  const [saved, setSaved] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    await api.patch(`/assessments/${assessment.id}`, form);
    setSaved(true);
    onChange();
    setTimeout(() => setSaved(false), 1500);
  }
  async function toggleArchive() {
    await api.post(`/assessments/${assessment.id}/${assessment.status === "archived" ? "restore" : "archive"}`);
    onChange();
  }
  async function remove() {
    if (!confirm("Permanently delete this assessment and all its jobs/tokens?")) return;
    await api.del(`/assessments/${assessment.id}`);
    nav("/");
  }

  return (
    <div className="grid" style={{ maxWidth: 640 }}>
      <form className="card" onSubmit={save}>
        <div className="field"><label>Name</label>
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
        <div className="field"><label>Client</label>
          <input value={form.client} onChange={(e) => setForm({ ...form, client: e.target.value })} /></div>
        <div className="field"><label>Description</label>
          <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
        <div className="field"><label>Scope / Rules of engagement</label>
          <textarea value={form.scope_notes} onChange={(e) => setForm({ ...form, scope_notes: e.target.value })} /></div>
        <div className="row">
          <button className="btn-primary">Save</button>
          {saved && <span className="badge success">Saved</span>}
        </div>
      </form>
      <div className="card row between">
        <div>
          <strong>{assessment.status === "archived" ? "Restore" : "Archive"} assessment</strong>
          <div className="muted">Archived assessments are kept for historical reference.</div>
        </div>
        <button onClick={toggleArchive}>{assessment.status === "archived" ? "Restore" : "Archive"}</button>
      </div>
      <div className="card row between">
        <div>
          <strong className="line-error">Delete assessment</strong>
          <div className="muted">Removes the assessment and all associated jobs and tokens.</div>
        </div>
        <button className="btn-danger" onClick={remove}>Delete</button>
      </div>
    </div>
  );
}
