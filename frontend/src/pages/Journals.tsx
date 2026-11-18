// Journal entry testing: score every journal in a ledger extract, explain the riskiest, record decisions.
import { useEffect, useState } from "react";
import { api, fmtDate } from "../api";
import { can, useUser } from "../App";
import { Badge, Empty, Loading, useAction, useLoad } from "../components/ui";

const money = (n: number) => n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const DISP: Record<string, string> = { open: "Not reviewed", selected: "Selected for testing", cleared: "Checked, no issue", exception: "Exception" };

export default function JournalsTab({ eng, locked }: { eng: any; locked: boolean }) {
  const user = useUser();
  const [batches, reload] = useLoad<any[]>(() => api.get(`/engagements/${eng.id}/journals`), [eng.id]);
  const [bid, setBid] = useState<number | null>(null);
  const { busy, run } = useAction();
  if (!batches) return <Loading />;
  const b = batches.find((x) => x.id === bid) ?? batches[0];
  const upload = (file: File) => run(async () => {
    const fd = new FormData(); fd.append("file", file);
    const r = await api.post(`/engagements/${eng.id}/journals`, fd); setBid(r.id); reload();
  }, "Ledger scored");
  const sample = () => run(async () => { const r = await api.post(`/engagements/${eng.id}/journals/sample`); setBid(r.id); reload(); }, "Sample ledger loaded");

  if (!b) return (
    <div className="je-start">
      <h3>Journal entry testing</h3>
      <p className="muted">Upload the general ledger for the period. Every journal is scored against 15 checks for unusual entries, such as weekend postings, round amounts, entries just under approval limits and journals no one else approved. You then review the riskiest ones.</p>
      <p className="muted small">The file needs columns for journal ID, date, account and amount (or debit and credit). User, approver, posted time, source and description make more checks possible. CSV or Excel.</p>
      {!locked && <div className="row gap">
        <label className="filebtn primary">{busy ? "Scoring…" : "Upload ledger"}<input type="file" accept=".csv,.txt,.xlsx,.xlsm" disabled={busy} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} /></label>
        <button className="ghost" disabled={busy} onClick={sample}>Try with a sample ledger</button>
      </div>}
    </div>
  );
  return <Batch key={b.id} b={b} batches={batches} setBid={setBid} locked={locked} reload={reload} upload={upload} busy={busy}
    canDelete={can(user, "manager")} onDeleted={() => { setBid(null); reload(); }} />;
}

function Batch({ b, batches, setBid, locked, reload, upload, busy, canDelete, onDeleted }: any) {
  const s = b.stats;
  const [band, setBand] = useState("high");
  const [rule, setRule] = useState("");
  const [disp, setDisp] = useState("");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<number | null>(null);
  const [tick, setTick] = useState(0);
  const { run } = useAction();
  const [list] = useLoad<any>(() => api.get(`/journal-batches/${b.id}/entries?band=${band}&rule=${rule}&disposition=${disp}&q=${encodeURIComponent(q)}&limit=200`), [b.id, band, rule, disp, q, tick]);
  useEffect(() => { if (b.explain_status !== "running") return; const t = setTimeout(() => { reload(); setTick((x) => x + 1); }, 2000); return () => clearTimeout(t); }, [b, reload]);
  const maxRule = Math.max(1, ...s.rules.map((r: any) => r.count));
  return (
    <div className="stack">
      <div className="toolbar">
        <select value={b.id} onChange={(e) => setBid(Number(e.target.value))}>
          {batches.map((x: any) => <option key={x.id} value={x.id}>{x.filename} · {fmtDate(x.uploaded_at)}</option>)}
        </select>
        <span className="muted small">{s.period ? `${s.period[0]} to ${s.period[1]}` : ""} · sha {b.sha256.slice(0, 10)}</span>
        <div className="spacer" />
        <button className="ghost" onClick={() => run(() => api.download(`/journal-batches/${b.id}/export.csv`, `journal_testing_${b.id}.csv`))}>Export results</button>
        {!locked && <label className="filebtn ghost">{busy ? "Scoring…" : "Upload another ledger"}<input type="file" accept=".csv,.txt,.xlsx,.xlsm" disabled={busy} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} /></label>}
        {!locked && canDelete && <button className="ghost" onClick={() => confirm("Remove this ledger and its results?") && run(async () => { await api.del(`/journal-batches/${b.id}`); onDeleted(); }, "Ledger removed")}>Remove</button>}
      </div>

      <div className="kpis">
        <div className="kpi"><div className="kpi-n">{s.journals.toLocaleString()}</div><div className="kpi-l">Journals ({s.lines.toLocaleString()} lines)</div></div>
        <div className="kpi"><div className="kpi-n">{money(s.total_value)}</div><div className="kpi-l">Total value posted</div></div>
        <button className={`kpi kpi-btn bad ${band === "high" ? "on" : ""}`} onClick={() => setBand("high")}><div className="kpi-n">{s.bands.high}</div><div className="kpi-l">High risk (score 40+)</div></button>
        <button className={`kpi kpi-btn warn ${band === "medium" ? "on" : ""}`} onClick={() => setBand("medium")}><div className="kpi-n">{s.bands.medium}</div><div className="kpi-l">Medium risk (20 to 39)</div></button>
        <button className={`kpi kpi-btn ${band === "low" ? "on" : ""}`} onClick={() => setBand("low")}><div className="kpi-n">{s.bands.low.toLocaleString()}</div><div className="kpi-l">Low risk</div></button>
      </div>
      {s.skipped_rules.length > 0 && <div className="banner warn">Some checks could not run because the file has no column for them: {s.skipped_rules.join(", ")}.</div>}

      <div className={`je ${sel ? "with-detail" : ""}`}>
        <aside className="je-rules">
          <h4>Checks</h4>
          <button className={`rulebar ${rule === "" ? "on" : ""}`} onClick={() => setRule("")}><span>All checks</span></button>
          {s.rules.map((r: any) => (
            <button key={r.rule} className={`rulebar ${rule === r.rule ? "on" : ""}`} disabled={!r.count} onClick={() => { setRule(rule === r.rule ? "" : r.rule); setBand(""); }} title={`Adds ${r.weight} points`}>
              <span>{r.name}</span><b>{r.count}</b>
              <i style={{ width: `${(r.count / maxRule) * 100}%` }} />
            </button>
          ))}
          <p className="muted small">Scores are calculated by fixed rules, so the same file always gives the same result. Each check adds its points; 40 or more is high risk.</p>
        </aside>

        <section className="je-list">
          <div className="toolbar">
            <input placeholder="Search journal, description or user…" value={q} onChange={(e) => setQ(e.target.value)} />
            <select value={band} onChange={(e) => setBand(e.target.value)}><option value="">All risk levels</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select>
            <select value={disp} onChange={(e) => setDisp(e.target.value)}><option value="">All decisions</option>{Object.entries(DISP).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
            <div className="spacer" />
            {!locked && <button className="primary" disabled={b.explain_status === "running"} onClick={() => run(async () => { await api.post(`/journal-batches/${b.id}/explain`); reload(); })}>
              <span className="spark">✦</span> {b.explain_status === "running" ? "Writing explanations…" : b.explain_status === "done" ? "Explain more" : "Explain riskiest journals"}</button>}
          </div>
          {!list ? <Loading /> : list.items.length === 0 ? <Empty title="No journals match these filters" /> : (
            <table className="table">
              <thead><tr><th>Score</th><th>Journal</th><th>Date</th><th className="num">Amount</th><th>User</th><th>Description</th><th>Checks</th><th>Decision</th></tr></thead>
              <tbody>{list.items.map((e: any) => (
                <tr key={e.id} className={`rcm-row ${sel === e.id ? "sel" : ""}`} tabIndex={0} onClick={() => setSel(e.id)} onKeyDown={(k) => k.key === "Enter" && setSel(e.id)}>
                  <td><span className={`score ${e.band}`}>{e.score}</span></td>
                  <td><b>{e.ref}</b>{e.explained && <span className="spark" title="Explained"> ✦</span>}</td>
                  <td className="nowrap">{e.date ?? "—"}</td>
                  <td className="num">{money(e.amount)}</td>
                  <td>{e.user || "—"}</td>
                  <td className="rcm-text">{e.description || <span className="muted">No description</span>}</td>
                  <td>{e.rules.length}</td>
                  <td>{e.disposition === "open" ? <span className="muted">—</span> : <Badge v={e.disposition === "exception" ? "fail" : e.disposition === "cleared" ? "pass" : "running"} text={DISP[e.disposition]} />}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
          {list && list.total > list.items.length && <div className="muted small">Showing the top {list.items.length} of {list.total.toLocaleString()}. Use the filters to narrow down.</div>}
        </section>

        {sel && <Detail key={sel} id={sel} locked={locked} tick={tick} onClose={() => setSel(null)} onSaved={() => setTick((x) => x + 1)} />}
      </div>
    </div>
  );
}

function Detail({ id, locked, tick, onClose, onSaved }: any) {
  const [e, reload] = useLoad<any>(() => api.get(`/journal-entries/${id}`), [id, tick]);
  const [note, setNote] = useState("");
  const { busy, run } = useAction();
  useEffect(() => { if (e) setNote(e.disposition_note || ""); }, [e?.id, e?.disposition]);
  if (!e) return <aside className="pane je-detail"><Loading /></aside>;
  const decide = (d: string) => run(async () => { await api.patch(`/journal-entries/${id}`, { disposition: d, note }); reload(); onSaved(); }, "Decision saved");
  return (
    <aside className="pane je-detail">
      <div className="pane-head"><b>{e.ref}</b><span className={`score ${e.band}`}>{e.score}</span><span className="spacer" /><button className="icon" onClick={onClose} title="Close">×</button></div>
      <div className="pane-body">
        <div className="je-meta">
          <div><span className="field-l">Amount</span>{money(e.amount)}</div>
          <div><span className="field-l">Date</span>{e.date ?? "—"}</div>
          <div><span className="field-l">Posted</span>{e.posted_at ?? "—"}</div>
          <div><span className="field-l">Created by</span>{e.user || "—"}</div>
          <div><span className="field-l">Approved by</span>{e.approver || "—"}</div>
          <div><span className="field-l">Source</span>{e.source || "—"}</div>
        </div>
        <div><span className="field-l">Description</span><div>{e.description || <span className="muted">None</span>}</div></div>

        {e.explanation ? (
          <div className="je-why">
            <div><span className="spark">✦</span> <b>Why it stands out</b></div>
            <div>{e.explanation.why_unusual}</div>
            <b>What to check</b>
            <ul>{e.explanation.what_to_check.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul>
            <div className="muted small">{e.explanation.model}</div>
          </div>
        ) : e.score >= 20 && <div className="muted small">No explanation yet. Use “Explain riskiest journals” above the list.</div>}

        <h4>Checks triggered</h4>
        {e.hits.length === 0 ? <div className="muted">None.</div> : e.hits.map((h: any) => (
          <div key={h.rule} className="je-hit"><span><b>{h.name}</b><span className="muted small"> {h.reason}</span></span><span className="muted small">+{h.weight}</span></div>
        ))}

        <h4>Lines ({e.line_count})</h4>
        <table className="table compact">
          <thead><tr><th>Account</th><th className="num">Debit</th><th className="num">Credit</th></tr></thead>
          <tbody>{e.lines.map((l: any, i: number) => (
            <tr key={i}><td>{l.account} <span className="muted">{l.account_name}</span></td><td className="num">{l.debit ? money(l.debit) : ""}</td><td className="num">{l.credit ? money(l.credit) : ""}</td></tr>
          ))}</tbody>
        </table>

        <h4>Your decision</h4>
        <div>{e.disposition === "open" ? <span className="muted">Not reviewed yet</span> : <Badge v={e.disposition === "exception" ? "fail" : e.disposition === "cleared" ? "pass" : "running"} text={DISP[e.disposition]} />}</div>
        {!locked && (
          <>
            <textarea rows={3} placeholder="What you checked and what you found" value={note} onChange={(x) => setNote(x.target.value)} />
            <div className="row gap">
              <button className="ghost sm" disabled={busy} onClick={() => decide("selected")}>Select for testing</button>
              <button className="ghost sm" disabled={busy} onClick={() => decide("cleared")}>Checked, no issue</button>
              <button className="ghost sm" disabled={busy} onClick={() => decide("exception")}>Raise exception</button>
            </div>
            <div className="muted small">A note is needed to clear a journal or raise an exception. Every decision is logged.</div>
          </>
        )}
      </div>
    </aside>
  );
}
