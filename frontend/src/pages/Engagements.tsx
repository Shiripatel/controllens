import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { can, useUser } from "../App";
import { Empty, ErrorBox, Loading, Modal, useAction, useLoad, Badge } from "../components/ui";

const initials = (n: string) => n.split(" ").map((x) => x[0]).join("").slice(0, 2).toUpperCase();

/** One bar split by stage: not started · design · operating · complete. */
function StageBar({ s }: { s: any }) {
  const b = s.by_status;
  const parts = [
    ["Not started", b.not_started, "p0"],
    ["Design", b.design_in_progress + b.design_prepared + b.design_reviewed, "p1"],
    ["Operating", b.operating_in_progress + b.operating_prepared, "p2"],
    ["Complete", b.operating_reviewed, "p3"],
  ] as [string, number, string][];
  return (
    <div>
      <div className="stagebar" title={parts.map(([l, n]) => `${l}: ${n}`).join(" · ")}>
        {parts.filter(([, n]) => n > 0).map(([l, n, c]) => <span key={l} className={c} style={{ flex: n }}>{n}</span>)}
        {s.controls === 0 && <span className="p0" style={{ flex: 1 }}>0</span>}
      </div>
      <div className="muted small">{s.complete} of {s.controls} complete</div>
    </div>
  );
}

export function RequestPills({ r }: { r: any }) {
  const total = r.open + r.received + r.closed;
  if (!total) return <span className="muted">—</span>;
  return (
    <span className="pills" title={`${r.open} open · ${r.received} received · ${r.closed} closed`}>
      {r.open > 0 && <span className="pill open">{r.open}</span>}
      {r.received > 0 && <span className="pill recv">{r.received}</span>}
      {r.closed > 0 && <span className="pill done">{r.closed}</span>}
    </span>
  );
}

export default function Engagements() {
  const user = useUser();
  const nav = useNavigate();
  const [list, , err] = useLoad<any[]>(() => api.get("/engagements"), []);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [client, setClient] = useState("");
  const [status, setStatus] = useState("");
  const rows = useMemo(() => (list ?? []).filter((e) =>
    (!client || e.client === client) && (!status || e.status === status) &&
    (!q || `${e.client} ${e.name} ${e.engagement_type}`.toLowerCase().includes(q.toLowerCase()))), [list, q, client, status]);
  if (err) return <ErrorBox msg={err} />;
  if (!list) return <Loading />;
  const clients = [...new Set(list.map((e) => e.client))].sort();
  const count = (s: string) => list.filter((e) => e.status === s).length;
  const sum = (f: (e: any) => number) => list.reduce((a, e) => a + f(e), 0);
  return (
    <div className="page">
      <div className="page-head">
        <div><h1>Engagements <span className="muted">({list.length})</span></h1><p className="muted">Everything you are working on, in one place</p></div>
        {can(user, "manager") && <button className="primary" onClick={() => setOpen(true)}>New engagement</button>}
      </div>
      <div className="sumrow">
        <button className={`sum ${status === "active" ? "on" : ""}`} onClick={() => setStatus(status === "active" ? "" : "active")}><b>{count("active")}</b> Active</button>
        <button className={`sum ${status === "locked" ? "on" : ""}`} onClick={() => setStatus(status === "locked" ? "" : "locked")}><b>{count("locked")}</b> Locked</button>
        <button className={`sum ${status === "archived" ? "on" : ""}`} onClick={() => setStatus(status === "archived" ? "" : "archived")}><b>{count("archived")}</b> Archived</button>
        <span className="sum plain"><b>{sum((e) => e.stats.requests.open)}</b> Open requests</span>
        <span className="sum plain"><b>{sum((e) => e.stats.open_notes)}</b> Open review notes</span>
        <span className={`sum plain ${sum((e) => e.stats.open_exceptions) ? "bad" : ""}`}><b>{sum((e) => e.stats.open_exceptions)}</b> Open exceptions</span>
      </div>
      <div className="toolbar">
        <input placeholder="Search engagements…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={client} onChange={(e) => setClient(e.target.value)}><option value="">All clients</option>{clients.map((c) => <option key={c}>{c}</option>)}</select>
        <select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All statuses</option><option value="active">Active</option><option value="locked">Locked</option><option value="archived">Archived</option></select>
      </div>
      {rows.length === 0 ? <Empty title={list.length ? "No engagements match" : "No engagements yet"}>{list.length ? "Clear the filters to see all." : "Ask a manager to add you to one."}</Empty> : (
        <table className="table">
          <thead><tr><th>Client</th><th>Engagement</th><th>Period</th><th>Lead</th><th style={{ width: "22%" }}>Controls</th><th>Requests</th><th>Notes</th><th>Exceptions</th><th>Status</th></tr></thead>
          <tbody>{rows.map((e) => (
            <tr key={e.id} className="rcm-row" tabIndex={0} onClick={() => nav(`/engagements/${e.id}`)} onKeyDown={(k) => k.key === "Enter" && nav(`/engagements/${e.id}`)}>
              <td><b>{e.client}</b></td>
              <td>{e.name}<div className="muted small">{e.engagement_type}</div></td>
              <td className="nowrap small">{e.period_start}<br />{e.period_end}</td>
              <td><span className="lead"><span className="avatar sm">{initials(e.stats.lead || "?")}</span>{e.stats.lead}</span></td>
              <td><StageBar s={e.stats} /></td>
              <td><RequestPills r={e.stats.requests} /></td>
              <td>{e.stats.open_notes || <span className="muted">—</span>}</td>
              <td className={e.stats.open_exceptions ? "bad-text" : ""}>{e.stats.open_exceptions || <span className="muted">—</span>}</td>
              <td><Badge v={e.status === "active" ? "succeeded" : "low"} text={e.status} /></td>
            </tr>
          ))}</tbody>
        </table>
      )}
      <div className="legend muted small">
        Controls: <i className="p0" /> not started <i className="p1" /> design <i className="p2" /> operating <i className="p3" /> complete
        &nbsp;·&nbsp; Requests: <i className="open" /> open <i className="recv" /> received <i className="done" /> closed
      </div>
      {open && <NewEngagement onClose={() => setOpen(false)} />}
    </div>
  );
}

function NewEngagement({ onClose }: { onClose: () => void }) {
  const nav = useNavigate();
  const { busy, run } = useAction();
  const y = new Date().getFullYear();
  const [f, setF] = useState({ name: `FY${y} SOX ITGC`, client: "", engagement_type: "SOX ITGC", period_start: `${y}-01-01`, period_end: `${y}-12-31` });
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal title="New engagement" onClose={onClose}>
      <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        const r = await run(() => api.post("/engagements", f), "Engagement created");
        if (r) nav(`/engagements/${r.id}`);
      }}>
        <label>Client<input value={f.client} onChange={set("client")} required /></label>
        <label>Engagement name<input value={f.name} onChange={set("name")} required /></label>
        <label>Type
          <select value={f.engagement_type} onChange={set("engagement_type")}>
            <option>SOX ITGC</option><option>Internal audit ITGC</option><option>SOC 1</option><option>SOC 2</option>
          </select>
        </label>
        <div className="grid2">
          <label>Period start<input type="date" value={f.period_start} onChange={set("period_start")} required /></label>
          <label>Period end<input type="date" value={f.period_end} onChange={set("period_end")} required /></label>
        </div>
        <div className="actions"><button type="button" className="ghost" onClick={onClose}>Cancel</button><button className="primary" disabled={busy}>Create</button></div>
      </form>
    </Modal>
  );
}
