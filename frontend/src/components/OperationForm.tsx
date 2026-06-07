import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Operation, VaultToken } from "../api/types";

const TOKEN_PRODUCING = ["auth", "phish-capture", "refresh", "auth-app", "auth-interactive"];

export function OperationForm({
  assessmentId,
  op,
  onLaunched,
}: {
  assessmentId: number;
  op: Operation;
  onLaunched: (jobId: number) => void;
}) {
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [tokens, setTokens] = useState<VaultToken[]>([]);
  const [saveAs, setSaveAs] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const hasTokenField = op.fields.some((f) => f.type === "token");
  const isTokenProducing = TOKEN_PRODUCING.includes(op.activity);

  useEffect(() => {
    // reset on op change
    const init: Record<string, unknown> = {};
    op.fields.forEach((f) => {
      if (f.default !== null && f.default !== undefined) init[f.name] = f.default;
    });
    setValues(init);
    setError("");
    setSaveAs("");
    if (hasTokenField) {
      api.get<VaultToken[]>(`/assessments/${assessmentId}/tokens`).then(setTokens);
    }
  }, [op.activity, assessmentId]);

  function set(name: string, value: unknown) {
    setValues((v) => ({ ...v, [name]: value }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const params: Record<string, unknown> = {};
      Object.entries(values).forEach(([k, v]) => {
        if (v !== "" && v !== undefined && v !== null) params[k] = v;
      });
      const job = await api.post<{ id: number }>(
        `/assessments/${assessmentId}/operations`,
        {
          activity: op.activity,
          params,
          label: op.name,
          check_privileges: !!values["check_privileges"],
          save_token_as: isTokenProducing && saveAs ? saveAs : undefined,
        }
      );
      onLaunched(job.id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to launch");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <p className="muted" style={{ marginTop: 0 }}>{op.description}</p>
      {op.long_running && (
        <div className="notice" style={{ marginBottom: 14 }}>
          Long-running job — output streams live and can be cancelled.
        </div>
      )}
      {error && <div className="error-banner">{error}</div>}

      {op.fields.map((f) => (
        <div className="field" key={f.name}>
          {f.type === "bool" ? (
            <div className="checkbox">
              <input
                type="checkbox"
                id={f.name}
                checked={!!values[f.name]}
                onChange={(e) => set(f.name, e.target.checked)}
              />
              <label htmlFor={f.name}>{f.label}</label>
            </div>
          ) : f.type === "token" ? (
            <>
              <label>{f.label}</label>
              <select
                value={(values[f.name] as string) || ""}
                onChange={(e) => set(f.name, e.target.value ? Number(e.target.value) : "")}
              >
                <option value="">— select stored token —</option>
                {tokens.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} {t.username ? `(${t.username})` : ""}{t.is_expired ? " · EXPIRED" : ""}
                  </option>
                ))}
              </select>
              {f.help && <small>{f.help}</small>}
            </>
          ) : f.type === "select" ? (
            <>
              <label>{f.label}</label>
              <select
                value={(values[f.name] as string) || ""}
                onChange={(e) => set(f.name, e.target.value)}
              >
                {f.options.map((o) => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
            </>
          ) : f.type === "textarea" ? (
            <>
              <label>{f.label}{f.required ? " *" : ""}</label>
              <textarea
                value={(values[f.name] as string) || ""}
                placeholder={f.placeholder}
                required={f.required}
                onChange={(e) => set(f.name, e.target.value)}
              />
              {f.help && <small>{f.help}</small>}
            </>
          ) : (
            <>
              <label>{f.label}{f.required ? " *" : ""}</label>
              <input
                type={f.type === "password" ? "password" : f.type === "number" ? "number" : "text"}
                value={(values[f.name] as string) ?? ""}
                placeholder={f.placeholder}
                required={f.required}
                onChange={(e) =>
                  set(f.name, f.type === "number" ? Number(e.target.value) : e.target.value)
                }
              />
              {f.help && <small>{f.help}</small>}
            </>
          )}
        </div>
      ))}

      {isTokenProducing && (
        <div className="field">
          <label>Save resulting token to vault as (optional)</label>
          <input
            value={saveAs}
            placeholder="e.g. victim-graph"
            onChange={(e) => setSaveAs(e.target.value)}
          />
        </div>
      )}

      <button className="btn-primary" disabled={busy}>
        {busy ? "Launching…" : "Run operation"}
      </button>
    </form>
  );
}
