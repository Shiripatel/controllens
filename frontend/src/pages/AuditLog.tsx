import { useState } from "react";
import { api } from "../api";
import { useAction } from "../components/ui";
import { Activity } from "./Engagement";

export default function AuditLogPage() {
  const [action, setAction] = useState("");
  const [v, setV] = useState<any>(null);
  const { busy, run } = useAction();
  return (
    <div className="page">
      <div className="page-head">
        <div><h1>Audit trail</h1><p className="muted">Every action, agent run and sign-off. Rows are hash-chained so any edit or deletion is detected.</p></div>
        <button className="primary" disabled={busy} onClick={() => run(async () => setV(await api.get("/audit/verify")))}>Verify integrity</button>
      </div>
      {v && <div className={`banner ${v.valid ? "good" : "bad"}`}>{v.valid ? `Chain intact — ${v.checked} entries verified.` : `Chain BROKEN at entry #${v.broken_at_id} (after ${v.checked} good entries). The log was changed outside the application.`}</div>}
      <div className="toolbar">
        <select value={action} onChange={(e) => setAction(e.target.value)}>
          <option value="">All actions</option>
          {["auth", "engagement", "control", "evidence", "sample", "agent", "conclusion", "signoff", "note", "exception", "user"].map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
      </div>
      <Activity path={`/audit?limit=500${action ? `&action=${action}` : ""}`} />
    </div>
  );
}
