// Evidence tab (with intake check), citation viewer, and the evidence request list.
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api, fmtDate, fmtSize } from "../api";
import { Badge, Empty, Loading, Modal, useAction, useLoad } from "../components/ui";

const isImage = (name: string) => /\.(png|jpe?g)$/i.test(name);
const isPdf = (name: string) => /\.pdf$/i.test(name);

// ------------------------------------------------------------ evidence viewer
/** Shows one evidence file. If an excerpt is given, it is highlighted in the text. */
export function EvidenceViewer({ id, excerpt, onClose }: { id: number; excerpt?: string; onClose: () => void }) {
  const [doc] = useLoad<any>(() => api.get(`/evidence/${id}/text`), [id]);
  const [url, setUrl] = useState<string | null>(null);
  const visual = doc && (isImage(doc.filename) || (isPdf(doc.filename) && !doc.text?.trim()));
  useEffect(() => {
    if (!visual) return;
    let made: string | null = null;
    api.blobUrl(`/evidence/${id}/download`).then((u) => { made = u; setUrl(u); }).catch(() => {});
    return () => { if (made) URL.revokeObjectURL(made); };
  }, [visual, id]);

  const body: ReactNode = useMemo(() => {
    if (!doc || visual) return null;
    const text: string = doc.text || "(no readable text)";
    if (!excerpt?.trim()) return text;
    // match the quote while ignoring differences in spacing and letter case
    const pattern = excerpt.trim().split(/\s+/).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\s+");
    const m = new RegExp(pattern, "i").exec(text);
    if (!m) return text;
    return <>{text.slice(0, m.index)}<mark id="hit">{m[0]}</mark>{text.slice(m.index + m[0].length)}</>;
  }, [doc, excerpt, visual]);

  useEffect(() => { document.getElementById("hit")?.scrollIntoView({ block: "center" }); }, [body]);
  const found = !!excerpt && !visual && !!doc && typeof body !== "string";

  return (
    <Modal title={doc ? `E${id} · ${doc.filename}` : `E${id}`} onClose={onClose} wide>
      {!doc ? <Loading /> : (
        <>
          {excerpt && (
            <div className={`banner ${visual ? "info" : found ? "good" : "warn"}`}>
              <b>Agent's quote:</b> “{excerpt}”
              <div className="small">{visual ? "This is an image or scan. Check the quote by eye." : found ? "Found in the file and highlighted below." : "Not found word for word in this file."}</div>
            </div>
          )}
          <div className="muted small">{doc.note}</div>
          {visual
            ? (url ? (isImage(doc.filename) ? <img className="evimg" src={url} alt={doc.filename} /> : <iframe className="evpdf" src={url} title={doc.filename} />) : <Loading />)
            : <pre className="doc">{body}</pre>}
        </>
      )}
    </Modal>
  );
}

/** Evidence quotes behind an agent's claim. Click one to open the file at that quote. */
export function Citations({ list }: { list: any[] }) {
  const [open, setOpen] = useState<any>(null);
  if (!list?.length) return <span className="muted small">No evidence cited</span>;
  return (
    <div className="cites">
      {list.map((x, i) => {
        const id = Number(String(x.evidence_id).replace(/\D/g, ""));
        return (
          <button key={i} className="cite" title="Open the evidence at this quote" onClick={() => id && setOpen({ id, excerpt: x.excerpt })}>
            <span className={`ver ${x.verified === true ? "ok" : x.verified === false ? "no" : "na"}`}>{x.verified === true ? "✓" : x.verified === false ? "✗" : "?"}</span>
            <span className="mono">{x.evidence_id}</span>{x.locator && <span className="muted small"> {x.locator}</span>} <q>{x.excerpt}</q>
            {x.visual && <span className="muted small"> · image, check by eye</span>}
          </button>
        );
      })}
      {open && <EvidenceViewer id={open.id} excerpt={open.excerpt} onClose={() => setOpen(null)} />}
    </div>
  );
}

// --------------------------------------------------------------- evidence tab
export function EvidenceTab({ c, evidence, locked, refresh }: any) {
  const [file, setFile] = useState<File | null>(null);
  const [purpose, setPurpose] = useState("design");
  const [desc, setDesc] = useState("");
  const [reqId, setReqId] = useState("");
  const [view, setView] = useState<number | null>(null);
  const [requests, reloadReq] = useLoad<any[]>(() => api.get(`/controls/${c.id}/requests`), [c.id]);
  const { busy, run } = useAction();
  const pending = evidence.some((e: any) => e.intake_status === "pending");
  useEffect(() => { if (!pending) return; const t = setTimeout(refresh, 2000); return () => clearTimeout(t); }, [pending, evidence, refresh]);
  const openReqs = (requests ?? []).filter((r) => r.status !== "closed");
  const attrText = (id: string) => c.attributes.find((a: any) => a.id === id)?.text ?? id;
  return (
    <>
      {!locked && (
        <form className="card upload" onSubmit={async (e) => {
          e.preventDefault();
          if (!file) return;
          const fd = new FormData();
          fd.append("file", file); fd.append("purpose", purpose); fd.append("description", desc);
          if (reqId) fd.append("request_id", reqId);
          if (await run(() => api.post(`/controls/${c.id}/evidence`, fd), "Uploaded. Running intake check…")) {
            setFile(null); setDesc(""); setReqId(""); (e.target as HTMLFormElement).reset(); refresh(); reloadReq();
          }
        }}>
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} accept=".pdf,.txt,.csv,.log,.md,.json,.xml,.xlsx,.xlsm,.docx,.png,.jpg,.jpeg,.eml" />
          <select value={purpose} onChange={(e) => setPurpose(e.target.value)}>
            <option value="design">Design / walkthrough</option>
            <option value="population">Population (for sampling)</option>
            <option value="operating">Operating test evidence</option>
            <option value="general">General</option>
          </select>
          {openReqs.length > 0 && (
            <select value={reqId} onChange={(e) => setReqId(e.target.value)}>
              <option value="">Not for a request</option>
              {openReqs.map((r) => <option key={r.id} value={r.id}>For: {r.title.slice(0, 50)}</option>)}
            </select>
          )}
          <input placeholder="Description (optional)" value={desc} onChange={(e) => setDesc(e.target.value)} />
          <button className="primary" disabled={!file || busy}>{busy ? "Uploading…" : "Upload"}</button>
          <div className="muted small full">PDF, Excel, Word, CSV, text, and screenshots (PNG / JPG). Scanned PDFs and screenshots are read by the AI as images.</div>
        </form>
      )}
      {evidence.length === 0 ? <Empty title="No evidence yet">Upload the policy, walkthrough, population and sample evidence. Expected: {c.expected_evidence.join(", ")}.</Empty> : (
        <div className="stack">
          {evidence.map((e: any) => {
            const k = e.intake || {};
            return (
              <div key={e.id} className="card evcard">
                <div className="row between">
                  <div className="row gap">
                    <span className="mono ref">{e.label}</span><b>{e.filename}</b><Badge v="low" text={e.purpose} />
                    {e.visual && <Badge v="info" text={c.ai_provider === "mock" ? "image (needs AI key)" : "read as image"} />}
                    <span className="muted small">{fmtSize(e.size)} · {fmtDate(e.uploaded_at)} · <span className="mono" title={e.sha256}>sha {e.sha256.slice(0, 10)}…</span></span>
                  </div>
                  <div className="row gap nowrap">
                    <button className="ghost sm" onClick={() => setView(e.id)}>View</button>
                    <button className="ghost sm" onClick={() => run(() => api.download(`/evidence/${e.id}/download`, e.filename))}>Download</button>
                    {!locked && <button className="ghost sm" onClick={() => run(async () => { await api.post(`/evidence/${e.id}/intake`); refresh(); })}>Re-check</button>}
                    {!locked && <button className="ghost sm" onClick={() => confirm(`Remove ${e.filename}? The record stays in the audit trail.`) && run(async () => { await api.del(`/evidence/${e.id}`); refresh(); }, "Evidence removed")}>Remove</button>}
                  </div>
                </div>
                {e.intake_status === "pending" && <div className="intake muted small"><span className="spark">✦</span> Intake check running…</div>}
                {e.intake_status === "failed" && <div className="intake warn-text small">Intake check failed: {k.error}</div>}
                {e.intake_status === "done" && (
                  <div className="intake">
                    <div><span className="spark dark">✦</span> <b>{k.doc_type}</b>. {k.summary}</div>
                    <div className="row gap small">
                      <span className="muted">Period: {k.period_covered}</span><span className="muted">System: {k.system_identified}</span>
                      {k.supports_attributes?.length > 0 && <span>Supports: {k.supports_attributes.map((a: string) => <span key={a} className="chip" title={attrText(a)}>{a}</span>)}</span>}
                    </div>
                    {k.quality_issues?.length > 0 && <ul className="issues">{k.quality_issues.map((q: string, i: number) => <li key={i}>{q}</li>)}</ul>}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      {view && <EvidenceViewer id={view} onClose={() => setView(null)} />}
    </>
  );
}

// --------------------------------------------------------------- requests tab
export function RequestsTab({ c, evidence, locked, refresh }: any) {
  const [list, reload] = useLoad<any[]>(() => api.get(`/controls/${c.id}/requests`), [c.id]);
  const [f, setF] = useState({ title: "", detail: "", due_date: "" });
  const { busy, run } = useAction();
  if (!list) return <Loading />;
  const done = () => { reload(); refresh(); };
  const label = (id: number) => evidence.find((e: any) => e.id === id)?.filename ?? `E${id}`;
  return (
    <div className="stack">
      <div className="agentbar">
        <div>
          <div className="agent-name"><span className="spark">✦</span> Evidence request list</div>
          <div className="muted small">Drafts requests from the Design agent's gaps, or from the standard evidence list if the agent has not run yet.</div>
        </div>
        {!locked && <button className="primary" disabled={busy} onClick={async () => {
          const r = await run(() => api.post<any[]>(`/controls/${c.id}/requests/draft`));
          if (r) { done(); }
        }}>Draft requests</button>}
      </div>
      {!locked && (
        <form className="card upload" onSubmit={async (e) => {
          e.preventDefault();
          if (await run(() => api.post(`/controls/${c.id}/requests`, { ...f, due_date: f.due_date || null }), "Request added")) { setF({ title: "", detail: "", due_date: "" }); done(); }
        }}>
          <input className="grow" placeholder="What do you need from the client?" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} required />
          <input type="date" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} title="Due date" />
          <button className="primary" disabled={busy}>Add request</button>
        </form>
      )}
      {list.length === 0 ? <Empty title="No requests yet">Click “Draft requests” to build the list for this control.</Empty> : (
        <table className="table">
          <thead><tr><th>Request</th><th>Due</th><th>Files received</th><th>Status</th></tr></thead>
          <tbody>{list.map((r) => (
            <tr key={r.id}>
              <td>{r.title}{r.source === "agent" && <span className="muted small"> · ✦ drafted</span>}{r.detail && <div className="muted small">{r.detail}</div>}</td>
              <td className="nowrap">{r.due_date ?? "—"}</td>
              <td>{r.evidence_ids.length ? r.evidence_ids.map((id: number) => <div key={id} className="small"><span className="mono">E{id}</span> {label(id)}</div>) : <span className="muted small">None. Upload on the Evidence tab and pick this request.</span>}</td>
              <td><select disabled={locked} value={r.status} onChange={(e) => run(async () => { await api.patch(`/requests/${r.id}`, { status: e.target.value }); done(); })}>
                <option value="open">Open</option><option value="received">Received</option><option value="closed">Closed</option></select></td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </div>
  );
}
