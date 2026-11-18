import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, fmtDate, label } from "../api";
import { can, useUser } from "../App";
import { RequestPills } from "./Engagements";
import { Badge, Empty, ErrorBox, Loading, Modal, Tabs, useAction, useLoad } from "../components/ui";

const DOMAINS = ["APD", "PC", "CO", "PD"];
const STAGES = ["not_started", "design_in_progress", "design_prepared", "design_reviewed", "operating_in_progress", "operating_prepared", "operating_reviewed"];

export default function EngagementPage() {
  const { eid } = useParams();
  const user = useUser();
  const [eng, reload, err] = useLoad<any>(() => api.get(`/engagements/${eid}`), [eid]);
  const [controls, reloadControls] = useLoad<any[]>(() => api.get(`/engagements/${eid}/controls`), [eid]);
  const [tab, setTab] = useState("controls");
  const { run } = useAction();
  if (err) return <ErrorBox msg={err} />;
  if (!eng || !controls) return <Loading />;
  const s = eng.stats;
  const locked = eng.status !== "active";
  return (
    <div className="page">
      <div className="crumbs"><Link to="/engagements">Engagements</Link> / {eng.client}</div>
      <div className="page-head">
        <div>
          <h1>{eng.name}</h1>
          <p className="muted">{eng.client} · {eng.engagement_type} · Period {eng.period_start} → {eng.period_end}</p>
        </div>
        <div className="row gap">
          <button className="ghost" onClick={() => run(() => api.download(`/engagements/${eid}/export.csv`, `${eng.client}_controls.csv`))}>Export CSV</button>
          {can(user, "manager") && (
            <button className="ghost" onClick={() => run(async () => { await api.patch(`/engagements/${eid}`, { status: locked ? "active" : "locked" }); reload(); }, locked ? "Engagement unlocked" : "Engagement locked")}>
              {locked ? "Unlock" : "Lock engagement"}
            </button>
          )}
        </div>
      </div>
      {locked && <div className="banner warn">This engagement is {eng.status}. Work papers are read-only.</div>}

      <div className="kpis">
        <Kpi n={s.controls} l="Controls in scope" />
        <Kpi n={s.complete} l="Complete (Operating reviewed)" />
        <Kpi n={s.open_notes} l="Open review notes" tone={s.open_notes ? "warn" : ""} />
        <Kpi n={s.open_exceptions} l="Open exceptions" tone={s.open_exceptions ? "bad" : ""} />
        <Kpi n={s.deficient} l="Deficient controls" tone={s.deficient ? "bad" : ""} />
      </div>

      <div className="card pipeline">
        {STAGES.map((st) => (
          <div key={st} className="pipe-step">
            <div className="pipe-n">{s.by_status[st] ?? 0}</div>
            <div className="pipe-l">{label(st)}</div>
          </div>
        ))}
      </div>

      <Tabs active={tab} onChange={setTab} tabs={[
        { key: "controls", label: "Risk & control matrix", count: controls.length },
        { key: "requests", label: "Evidence requests" },
        { key: "systems", label: "Systems", count: eng.systems.length },
        { key: "team", label: "Team", count: eng.members.length },
        { key: "activity", label: "Activity" },
      ]} />
      {tab === "controls" && <ControlsTab eng={eng} controls={controls} locked={locked} onChange={() => { reloadControls(); reload(); }} />}
      {tab === "requests" && <RequestsTracker eid={eng.id} client={eng.client} />}
      {tab === "systems" && <SystemsTab eng={eng} locked={locked} onChange={reload} />}
      {tab === "team" && <TeamTab eng={eng} onChange={reload} />}
      {tab === "activity" && <Activity path={`/audit?engagement_id=${eid}`} />}
    </div>
  );
}

function Kpi({ n, l, tone = "" }: { n: number; l: string; tone?: string }) {
  return <div className={`kpi ${tone}`}><div className="kpi-n">{n}</div><div className="kpi-l">{l}</div></div>;
}

const COLS: [string, string][] = [["risk", "Risk"], ["system", "System"], ["freq", "Frequency / nature"], ["rating", "Rating"], ["files", "Files"], ["requests", "Requests"], ["signoffs", "Sign-offs"]];
const COLS_DEFAULT: Record<string, boolean> = { risk: true, system: true, freq: false, rating: false, files: true, requests: true, signoffs: true };

function ControlsTab({ eng, controls, locked, onChange }: any) {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [dom, setDom] = useState("");
  const [st, setSt] = useState("");
  const [adding, setAdding] = useState(false);
  const [cols, setCols] = useState<Record<string, boolean>>(() => {
    try { return { ...COLS_DEFAULT, ...JSON.parse(localStorage.getItem("cl_rcm_cols") || "{}") }; } catch { return COLS_DEFAULT; }
  });
  const toggle = (k: string) => { const n = { ...cols, [k]: !cols[k] }; setCols(n); try { localStorage.setItem("cl_rcm_cols", JSON.stringify(n)); } catch { /* not saved */ } };
  const shown = COLS.filter(([k]) => cols[k]).length + 5;
  const rows = useMemo(() => controls.filter((c: any) =>
    (!dom || c.domain === dom) && (!st || c.status === st) &&
    (!q || `${c.ref} ${c.title} ${c.risk} ${c.description} ${c.system?.name ?? ""}`.toLowerCase().includes(q.toLowerCase()))), [controls, q, dom, st]);
  const groups = DOMAINS.map((d) => [d, rows.filter((c: any) => c.domain === d)] as [string, any[]]).filter(([, r]) => r.length);
  return (
    <>
      <div className="toolbar">
        <input placeholder="Search risks and controls…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={dom} onChange={(e) => setDom(e.target.value)}><option value="">All domains</option>{DOMAINS.map((d) => <option key={d} value={d}>{d} — {label(d)}</option>)}</select>
        <select value={st} onChange={(e) => setSt(e.target.value)}><option value="">All statuses</option>{STAGES.map((s) => <option key={s} value={s}>{label(s)}</option>)}</select>
        <div className="spacer" />
        <details className="colmenu"><summary className="ghost">Columns</summary>
          <div className="colmenu-b">{COLS.map(([k, l]) => <label key={k} className="check"><input type="checkbox" checked={cols[k]} onChange={() => toggle(k)} /> {l}</label>)}</div>
        </details>
        {!locked && <button className="primary" onClick={() => setAdding(true)}>Add controls</button>}
      </div>
      {rows.length === 0 ? <Empty title="No controls match">Add controls from the ITGC library.</Empty> : (
        <div className="rcm-wrap">
          <table className="table rcm">
            <thead><tr><th>Ref</th>{cols.risk && <th>Risk</th>}<th>Control</th>{cols.system && <th>System</th>}{cols.freq && <th>Frequency / nature</th>}{cols.rating && <th>Rating</th>}{cols.files && <th>Files</th>}{cols.requests && <th>Requests</th>}<th>Design</th><th>Operating</th>{cols.signoffs && <th>Sign-offs</th>}<th>Status</th></tr></thead>
            {groups.map(([d, list]) => (
              <tbody key={d}>
                <tr className="rcm-group"><td colSpan={shown}><b>{d}</b> · {label(d)} <span className="muted">({list.length})</span></td></tr>
                {list.map((c: any) => (
                  <tr key={c.id} className="rcm-row" tabIndex={0} onClick={() => nav(`/controls/${c.id}`)} onKeyDown={(e) => e.key === "Enter" && nav(`/controls/${c.id}`)}>
                    <td className="mono">{c.ref}{c.key_control && <div className="keytag">Key</div>}</td>
                    {cols.risk && <td className="rcm-text">{c.risk}</td>}
                    <td className="rcm-text"><b>{c.title}</b><div className="muted">{c.description}</div></td>
                    {cols.system && <td>{c.system?.name ?? "—"}</td>}
                    {cols.freq && <td>{c.frequency}<div className="muted small">{c.nature}</div></td>}
                    {cols.rating && <td><Badge v={c.risk_rating === "High" ? "high" : c.risk_rating === "Low" ? "low" : "medium"} text={c.risk_rating} /></td>}
                    {cols.files && <td>{c.files || <span className="muted">—</span>}</td>}
                    {cols.requests && <td><RequestPills r={c.requests} /></td>}
                    <td>{c.design_conclusion ? <Badge v={c.design_conclusion.design} /> : <span className="muted">—</span>}</td>
                    <td>{c.operating_conclusion ? <Badge v={c.operating_conclusion.operating} /> : <span className="muted">—</span>}{c.open_exceptions > 0 && <div className="bad-text small">{c.open_exceptions} exception(s)</div>}</td>
                    {cols.signoffs && <td className="signgrid">{[["design", "Design"], ["operating", "Operating"]].map(([k, l]) => (
                      <div key={k}><span className="muted small">{l}</span>
                        <span className={c.signed.includes(`${k}:prepare`) ? "tick on" : "tick"} title="Preparer">P</span>
                        <span className={c.signed.includes(`${k}:review`) ? "tick on" : "tick"} title="Reviewer">R</span></div>))}</td>}
                    <td><Badge v={c.status} /></td>
                  </tr>
                ))}
              </tbody>
            ))}
          </table>
        </div>
      )}
      {adding && <AddFromLibrary eng={eng} onClose={() => setAdding(false)} onDone={() => { setAdding(false); onChange(); }} />}
    </>
  );
}

function AddFromLibrary({ eng, onClose, onDone }: any) {
  const [lib] = useLoad<any>(() => api.get("/library"), []);
  const [refs, setRefs] = useState<string[]>([]);
  const [systems, setSystems] = useState<number[]>(eng.systems[0] ? [eng.systems[0].id] : []);
  const [risk, setRisk] = useState("Moderate");
  const { busy, run } = useAction();
  if (!lib) return <Modal title="Add controls" onClose={onClose}><Loading /></Modal>;
  const toggle = (arr: any[], v: any, set: any) => set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  return (
    <Modal title="Add controls from ITGC library" onClose={onClose} wide>
      <div className="grid2">
        <div>
          <h4>Systems in scope</h4>
          {eng.systems.length === 0 && <p className="muted small">No systems yet. Controls will be added without a system.</p>}
          {eng.systems.map((s: any) => (
            <label key={s.id} className="check"><input type="checkbox" checked={systems.includes(s.id)} onChange={() => toggle(systems, s.id, setSystems)} /> {s.name} <span className="muted">({s.layer})</span></label>
          ))}
        </div>
        <label>Risk rating<select value={risk} onChange={(e) => setRisk(e.target.value)}><option>Low</option><option>Moderate</option><option>High</option></select></label>
      </div>
      {DOMAINS.map((d) => {
        const items = lib.controls.filter((c: any) => c.domain === d);
        const all = items.every((c: any) => refs.includes(c.ref));
        return (
          <div key={d} className="libgroup">
            <div className="row between">
              <h4>{d} — {lib.domains[d]}</h4>
              <button className="ghost sm" onClick={() => setRefs(all ? refs.filter((r) => !items.some((c: any) => c.ref === r)) : [...new Set([...refs, ...items.map((c: any) => c.ref)])])}>{all ? "Clear" : "Select all"}</button>
            </div>
            {items.map((c: any) => (
              <label key={c.ref} className="check">
                <input type="checkbox" checked={refs.includes(c.ref)} onChange={() => toggle(refs, c.ref, setRefs)} />
                <span className="mono">{c.ref}</span> {c.title} <span className="muted small">· {c.frequency} · {c.nature}</span>
              </label>
            ))}
          </div>
        );
      })}
      <div className="actions">
        <span className="muted small">{refs.length * Math.max(1, systems.length)} control(s) will be created</span>
        <button className="ghost" onClick={onClose}>Cancel</button>
        <button className="primary" disabled={busy || !refs.length} onClick={async () => {
          const r = await run(() => api.post(`/engagements/${eng.id}/controls/from-library`, { refs, system_ids: systems.length ? systems : [null], risk_rating: risk }), "Controls added");
          if (r) onDone();
        }}>Add</button>
      </div>
    </Modal>
  );
}

function SystemsTab({ eng, locked, onChange }: any) {
  const [f, setF] = useState({ name: "", layer: "Application", description: "" });
  const { busy, run } = useAction();
  return (
    <div className="grid-side">
      <table className="table">
        <thead><tr><th>System</th><th>Layer</th><th>Description</th><th /></tr></thead>
        <tbody>
          {eng.systems.map((s: any) => (
            <tr key={s.id}><td>{s.name}</td><td>{s.layer}</td><td className="muted">{s.description}</td>
              <td>{!locked && <button className="ghost sm" onClick={() => run(async () => { await api.del(`/engagements/${eng.id}/systems/${s.id}`); onChange(); }, "System removed")}>Remove</button>}</td></tr>
          ))}
        </tbody>
      </table>
      {!locked && (
        <form className="card form" onSubmit={async (e) => {
          e.preventDefault();
          if (await run(() => api.post(`/engagements/${eng.id}/systems`, f), "System added")) { setF({ name: "", layer: "Application", description: "" }); onChange(); }
        }}>
          <h4>Add system</h4>
          <label>Name<input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required placeholder="e.g. Workday" /></label>
          <label>Layer<select value={f.layer} onChange={(e) => setF({ ...f, layer: e.target.value })}>{["Application", "Database", "OS", "Network", "Tool"].map((l) => <option key={l}>{l}</option>)}</select></label>
          <label>Description<input value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
          <button className="primary" disabled={busy}>Add</button>
        </form>
      )}
    </div>
  );
}

function TeamTab({ eng, onChange }: any) {
  const user = useUser();
  const [users] = useLoad<any[]>(() => api.get("/users"), []);
  const [pick, setPick] = useState("");
  const { run } = useAction();
  const memberIds = new Set(eng.members.map((m: any) => m.id));
  return (
    <div className="grid-side">
      <table className="table">
        <thead><tr><th>Name</th><th>Email</th><th>Role</th><th /></tr></thead>
        <tbody>{eng.members.map((m: any) => (
          <tr key={m.id}><td>{m.name}</td><td className="muted">{m.email}</td><td><Badge v="low" text={m.role} /></td>
            <td>{can(user, "manager") && m.id !== user.id && <button className="ghost sm" onClick={() => run(async () => { await api.del(`/engagements/${eng.id}/members/${m.id}`); onChange(); })}>Remove</button>}</td></tr>
        ))}</tbody>
      </table>
      {can(user, "manager") && users && (
        <div className="card form">
          <h4>Add team member</h4>
          <select value={pick} onChange={(e) => setPick(e.target.value)}>
            <option value="">Choose a user…</option>
            {users.filter((u) => !memberIds.has(u.id) && u.active).map((u) => <option key={u.id} value={u.id}>{u.name} ({u.role})</option>)}
          </select>
          <button className="primary" disabled={!pick} onClick={() => run(async () => { await api.post(`/engagements/${eng.id}/members`, { user_id: Number(pick) }); setPick(""); onChange(); }, "Member added")}>Add</button>
        </div>
      )}
    </div>
  );
}

export function Activity({ path }: { path: string }) {
  const [rows, , err] = useLoad<any[]>(() => api.get(path), [path]);
  if (err) return <ErrorBox msg={err} />;
  if (!rows) return <Loading />;
  if (!rows.length) return <Empty title="No activity yet" />;
  return (
    <table className="table compact">
      <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Details</th></tr></thead>
      <tbody>{rows.map((a) => (
        <tr key={a.id}><td className="nowrap">{fmtDate(a.at)}</td><td>{a.user_email}</td><td className="mono">{a.action}</td>
          <td className="details">{Object.entries(a.details || {}).slice(0, 4).map(([k, v]) => <span key={k}><b>{k}</b>: {typeof v === "object" ? JSON.stringify(v).slice(0, 80) : String(v).slice(0, 80)} </span>)}</td></tr>
      ))}</tbody>
    </table>
  );
}

function RequestsTracker({ eid, client }: { eid: number; client: string }) {
  const [rows] = useLoad<any[]>(() => api.get(`/engagements/${eid}/requests`), [eid]);
  const { run } = useAction();
  if (!rows) return <Loading />;
  const open = rows.filter((r) => r.status === "open").length;
  return (
    <>
      <div className="toolbar">
        <span className="muted">{rows.length} request(s) · {open} still open</span>
        <div className="spacer" />
        <button className="ghost" onClick={() => run(() => api.download(`/engagements/${eid}/requests.csv`, `${client}_evidence_requests.csv`))}>Export for client (CSV)</button>
      </div>
      {rows.length === 0 ? <Empty title="No evidence requests yet">Open a control and use the Requests tab to draft its list.</Empty> : (
        <table className="table">
          <thead><tr><th>Control</th><th>Request</th><th>Due</th><th>Files</th><th>Status</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.id}>
              <td className="mono"><Link to={`/controls/${r.control_id}`}>{r.control_ref}</Link></td>
              <td>{r.title}</td><td className="nowrap">{r.due_date ?? "—"}</td><td>{r.evidence_ids.length}</td>
              <td><Badge v={r.status === "open" ? "open" : r.status === "received" ? "addressed" : "closed"} text={r.status} /></td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </>
  );
}
