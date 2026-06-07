import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { Job, JobLog } from "../api/types";

const TERMINAL = ["completed", "failed", "cancelled"];

export function JobConsole({ jobId, onDone }: { jobId: number; onDone?: () => void }) {
  const [job, setJob] = useState<Job | null>(null);
  const [logs, setLogs] = useState<JobLog[]>([]);
  const lastId = useRef(0);
  const consoleRef = useRef<HTMLDivElement>(null);
  const notified = useRef(false);

  useEffect(() => {
    lastId.current = 0;
    setLogs([]);
    notified.current = false;
    let active = true;

    async function poll() {
      if (!active) return;
      try {
        const j = await api.get<Job>(`/jobs/${jobId}`);
        const newLogs = await api.get<JobLog[]>(`/jobs/${jobId}/logs?after=${lastId.current}`);
        if (!active) return;
        setJob(j);
        if (newLogs.length) {
          lastId.current = newLogs[newLogs.length - 1].id;
          setLogs((prev) => [...prev, ...newLogs]);
        }
        if (TERMINAL.includes(j.status)) {
          if (!notified.current) {
            notified.current = true;
            onDone?.();
          }
          return; // stop polling
        }
      } catch {
        /* keep trying */
      }
      setTimeout(poll, 1000);
    }
    poll();
    return () => {
      active = false;
    };
  }, [jobId]);

  useEffect(() => {
    consoleRef.current?.scrollTo(0, consoleRef.current.scrollHeight);
  }, [logs]);

  const running = job && !TERMINAL.includes(job.status);

  async function cancel() {
    await api.post(`/jobs/${jobId}/cancel`);
  }

  return (
    <div>
      <div className="row between" style={{ marginBottom: 10 }}>
        <div className="row">
          <strong>{job?.label || job?.activity || `Job #${jobId}`}</strong>
          {job && <span className={`badge ${job.status}`}>{job.status}</span>}
        </div>
        {running && (
          <button className="btn-sm btn-danger" onClick={cancel}>
            Cancel
          </button>
        )}
      </div>

      <div className="console" ref={consoleRef}>
        {logs.length === 0 && <span className="muted">Waiting for output…</span>}
        {logs.map((l) => (
          <div key={l.id} className={`line-${l.level}`}>
            <span className="ts">{l.ts.slice(11, 19)}</span>
            {l.message}
          </div>
        ))}
      </div>

      {job?.error && <div className="error-banner" style={{ marginTop: 12 }}>{job.error}</div>}

      {job && TERMINAL.includes(job.status) && job.result != null && (
        <div style={{ marginTop: 14 }}>
          <label>Result</label>
          <div className="json-view">{JSON.stringify(job.result, null, 2)}</div>
        </div>
      )}
    </div>
  );
}
