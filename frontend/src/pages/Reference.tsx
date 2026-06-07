import { useEffect, useState } from "react";
import { api } from "../api/client";

interface KnownId { name: string; appId: string; }
interface Category { category: string; count: number; }

export default function Reference() {
  const [tab, setTab] = useState<"apps" | "interest">("apps");
  return (
    <div>
      <h1 className="page-title">Reference</h1>
      <div className="muted" style={{ marginBottom: 16 }}>
        Built-in datasets shipped with AzureRedOps.
      </div>
      <div className="tabs">
        <div className={`tab ${tab === "apps" ? "active" : ""}`} onClick={() => setTab("apps")}>
          Known application IDs
        </div>
        <div className={`tab ${tab === "interest" ? "active" : ""}`} onClick={() => setTab("interest")}>
          Apps of interest
        </div>
      </div>
      {tab === "apps" ? <KnownApps /> : <Interest />}
    </div>
  );
}

function KnownApps() {
  const [search, setSearch] = useState("");
  const [items, setItems] = useState<KnownId[]>([]);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => {
      api.get<{ total: number; items: KnownId[] }>(
        `/reference/known-ids?search=${encodeURIComponent(search)}&limit=200`
      ).then((d) => {
        setItems(d.items);
        setTotal(d.total);
      });
    }, 200);
    return () => clearTimeout(t);
  }, [search]);

  return (
    <div className="grid" style={{ gap: 14 }}>
      <input
        placeholder="Search by name or app ID…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <div className="muted mono">{total} match(es) — showing up to 200</div>
      <div className="card" style={{ padding: 0 }}>
        <table>
          <thead><tr><th>Name</th><th>App ID</th></tr></thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.appId + a.name}>
                <td>{a.name}</td>
                <td className="mono">{a.appId}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Interest() {
  const [cats, setCats] = useState<Category[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [data, setData] = useState<Record<string, { [k: string]: string }[]>>({});

  useEffect(() => {
    api.get<Category[]>("/reference/interest/categories").then(setCats);
  }, []);

  function open(cat: string) {
    setActive(cat);
    api.get<Record<string, { [k: string]: string }[]>>(`/reference/interest?category=${cat}`).then(setData);
  }

  const list = active ? data[active] || [] : [];

  return (
    <div className="grid" style={{ gridTemplateColumns: "260px 1fr", alignItems: "start", gap: 16 }}>
      <div className="card" style={{ padding: 8 }}>
        {cats.map((c) => (
          <div
            key={c.category}
            className="tab"
            style={{
              display: "block", borderBottom: "none",
              borderLeft: active === c.category ? "2px solid var(--accent)" : "2px solid transparent",
              color: active === c.category ? "var(--text)" : "var(--muted)",
            }}
            onClick={() => open(c.category)}
          >
            {c.category} <span className="muted">({c.count})</span>
          </div>
        ))}
      </div>
      <div className="card" style={{ padding: 0 }}>
        {!active ? (
          <div className="empty">Pick a category.</div>
        ) : (
          <table>
            <thead><tr><th>Name</th><th>App ID</th></tr></thead>
            <tbody>
              {list.map((entry, i) => {
                const name = Object.keys(entry)[0];
                return (
                  <tr key={i}><td>{name}</td><td className="mono">{entry[name]}</td></tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
