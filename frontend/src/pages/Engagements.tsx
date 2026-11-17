import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { can, useUser } from "../App";
import { Empty, ErrorBox, Loading, Modal, useAction, useLoad, Badge } from "../components/ui";

export default function Engagements() {
  const user = useUser();
  const [list, , err] = useLoad<any[]>(() => api.get("/engagements"), []);
  const [open, setOpen] = useState(false);
  if (err) return <ErrorBox msg={err} />;
  if (!list) return <Loading />;
  return (
    <div className="page">
      <div className="page-head">
        <div><h1>Engagements</h1><p className="muted">ITGC testing engagements you can access</p></div>
        {can(user, "manager") && <button className="primary" onClick={() => setOpen(true)}>New engagement</button>}
      </div>
      {list.length === 0 ? <Empty title="No engagements yet">Ask a manager to add you to one.</Empty> : (
        <div className="cards">
          {list.map((e) => {
            const pct = e.stats.controls ? Math.round((e.stats.complete / e.stats.controls) * 100) : 0;
            return (
              <Link to={`/engagements/${e.id}`} key={e.id} className="card eng">
                <div className="row between"><span className="muted small">{e.client}</span><Badge v={e.status === "active" ? "succeeded" : "low"} text={e.status} /></div>
                <h3>{e.name}</h3>
                <div className="muted small">{e.engagement_type} · {e.period_start} → {e.period_end}</div>
                <div className="progress"><div style={{ width: `${pct}%` }} /></div>
                <div className="row between small">
                  <span>{e.stats.complete}/{e.stats.controls} controls complete</span>
                  <span className={e.stats.open_exceptions ? "bad-text" : "muted"}>{e.stats.open_exceptions} open exceptions</span>
                </div>
              </Link>
            );
          })}
        </div>
      )}
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
