import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, fmtDate, label } from "../api";
import { can, useUser } from "../App";
import { Badge, Empty, ErrorBox, Loading, Modal, Tabs, useAction, useLoad } from "../components/ui";
import { Activity } from "./Engagement";
import { Citations, EvidenceTab, RequestsTab } from "./Extras";

const FLOW = [
  ["not_started", "Not started"], ["design_in_progress", "Design"], ["design_prepared", "Design prepared"], ["design_reviewed", "Design reviewed"],
  ["operating_in_progress", "Operating"], ["operating_prepared", "Operating prepared"], ["operating_reviewed", "Complete"],
];

export default function ControlWorkspace() {
  const { cid } = useParams();
  const [c, reload, err] = useLoad<any>(() => api.get(`/controls/${cid}`), [cid]);
  const [evidence, reloadEv] = useLoad<any[]>(() => api.get(`/controls/${cid}/evidence`), [cid]);
  const [notes, reloadNotes] = useLoad<any[]>(() => api.get(`/controls/${cid}/notes`), [cid]);
  const [tab, setTab] = useState("design");
  if (err) return <ErrorBox msg={err} />;
  if (!c || !evidence || !notes) return <Loading />;
  const idx = FLOW.findIndex(([k]) => k === c.status);
  const locked = c.engagement.status !== "active";
  const openNotes = notes.filter((n) => n.status !== "closed").length;
  const refresh = () => { reload(); reloadEv(); reloadNotes(); };
  const props = { c, evidence, notes, locked, refresh };
  return (
    <div className="page">
      <div className="crumbs"><Link to="/engagements">Engagements</Link> / <Link to={`/engagements/${c.engagement.id}`}>{c.engagement.client} — {c.engagement.name}</Link> / {c.ref}</div>
      <div className="page-head">
        <div>
          <div className="row gap"><span className="mono ref">{c.ref}</span><Badge v={c.status} /><span className="muted small">{label(c.domain)}</span></div>
          <h1>{c.title}</h1>
          <p className="muted">{c.system?.name ?? "No system"} · {c.frequency} · {c.nature} · {c.risk_rating} risk {c.key_control ? "· Key control" : ""}</p>
        </div>
        <button className="ghost" onClick={() => api.download(`/controls/${c.id}/workpaper.html`, `${c.ref}_workpaper.html`)}>Export work paper</button>
      </div>
      {locked && <div className="banner warn">Engagement is {c.engagement.status}; this control is read-only.</div>}
      <div className="stepper">
        {FLOW.map(([k, l], i) => <div key={k} className={`st ${i < idx ? "done" : i === idx ? "now" : ""}`}><span className="dot" />{l}</div>)}
      </div>
      <Tabs active={tab} onChange={setTab} tabs={[
        { key: "overview", label: "Control" },
        { key: "evidence", label: "Evidence", count: evidence.length },
        { key: "requests", label: "Requests" },
        { key: "design", label: "Design Effectiveness" },
        { key: "sampling", label: "Sampling" },
        { key: "operating", label: "Operating Effectiveness" },
        { key: "review", label: "Review notes", count: openNotes },
        { key: "activity", label: "Activity" },
      ]} />
      {tab === "overview" && <Overview {...props} />}
      {tab === "evidence" && <EvidenceTab {...props} />}
      {tab === "requests" && <RequestsTab {...props} />}
      {tab === "design" && <StageTab stage="design" {...props} />}
      {tab === "sampling" && <SamplingTab {...props} />}
      {tab === "operating" && <StageTab stage="operating" {...props} />}
      {tab === "review" && <ReviewTab {...props} />}
      {tab === "activity" && <Activity path={`/controls/${cid}/activity`} />}
    </div>
  );
}

// ------------------------------------------------------------------ overview
function Overview({ c, locked, refresh }: any) {
  const [edit, setEdit] = useState(false);
  const [f, setF] = useState<any>(null);
  const [users] = useLoad<any[]>(() => api.get("/users"), []);
  const { busy, run } = useAction();
  const start = () => { setF({ ...c, attributes: c.attributes.map((a: any) => ({ ...a })) }); setEdit(true); };
  const userName = (id: number) => users?.find((u) => u.id === id)?.name ?? "—";
  if (edit && f) {
    const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
    return (
      <div className="card form">
        <div className="banner info">Changing the control definition revokes design and operating sign-offs.</div>
        <label>Title<input value={f.title} onChange={set("title")} /></label>
        <label>Description<textarea rows={3} value={f.description} onChange={set("description")} /></label>
        <div className="grid2">
          <label>Objective<textarea rows={2} value={f.objective} onChange={set("objective")} /></label>
          <label>Risk<textarea rows={2} value={f.risk} onChange={set("risk")} /></label>
        </div>
        <div className="grid3">
          <label>Frequency<select value={f.frequency} onChange={set("frequency")}>{["Annual", "Quarterly", "Monthly", "Weekly", "Daily", "Multiple times per day", "Event-driven", "Continuous (automated)"].map((x) => <option key={x}>{x}</option>)}</select></label>
          <label>Nature<select value={f.nature} onChange={set("nature")}>{["Manual", "IT-dependent manual", "Automated"].map((x) => <option key={x}>{x}</option>)}</select></label>
          <label>Risk rating<select value={f.risk_rating} onChange={set("risk_rating")}>{["Low", "Moderate", "High"].map((x) => <option key={x}>{x}</option>)}</select></label>
        </div>
        <div className="grid2">
          <label>Preparer<select value={f.preparer_id ?? ""} onChange={(e) => setF({ ...f, preparer_id: e.target.value ? Number(e.target.value) : null })}><option value="">—</option>{users?.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></label>
          <label>Reviewer<select value={f.reviewer_id ?? ""} onChange={(e) => setF({ ...f, reviewer_id: e.target.value ? Number(e.target.value) : null })}><option value="">—</option>{users?.filter((u) => ["reviewer", "manager", "admin"].includes(u.role)).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></label>
        </div>
        <h4>Attributes</h4>
        {f.attributes.map((a: any, i: number) => (
          <div key={i} className="row gap">
            <span className="mono">{a.id}</span>
            <input className="grow" value={a.text} onChange={(e) => { const x = [...f.attributes]; x[i] = { ...a, text: e.target.value }; setF({ ...f, attributes: x }); }} />
            <button className="ghost sm" onClick={() => setF({ ...f, attributes: f.attributes.filter((_: any, j: number) => j !== i) })}>Remove</button>
          </div>
        ))}
        <button className="ghost sm" onClick={() => {
          const n = Math.max(0, ...f.attributes.map((a: any) => Number(a.id.slice(1)) || 0)) + 1;
          setF({ ...f, attributes: [...f.attributes, { id: `A${n}`, text: "" }] });
        }}>+ Add attribute</button>
        <div className="actions">
          <button className="ghost" onClick={() => setEdit(false)}>Cancel</button>
          <button className="primary" disabled={busy} onClick={async () => {
            const body = { row_version: c.row_version, ...Object.fromEntries(["title", "description", "objective", "risk", "frequency", "nature", "risk_rating", "attributes", "preparer_id", "reviewer_id"].map((k) => [k, f[k]])) };
            if (await run(() => api.patch(`/controls/${c.id}`, body), "Control saved")) { setEdit(false); refresh(); }
          }}>Save</button>
        </div>
      </div>
    );
  }
  return (
    <div className="grid-side">
      <div className="card">
        <Field l="Description">{c.description}</Field>
        <Field l="Control objective">{c.objective}</Field>
        <Field l="Risk addressed">{c.risk}</Field>
        <h4>Attributes</h4>
        <ol className="attrs">{c.attributes.map((a: any) => <li key={a.id}><span className="mono">{a.id}</span> {a.text}</li>)}</ol>
        <div className="grid2">
          <div><h4>Design procedures</h4><ul>{c.design_procedures.map((p: string, i: number) => <li key={i}>{p}</li>)}</ul></div>
          <div><h4>Operating procedures</h4><ul>{c.operating_procedures.map((p: string, i: number) => <li key={i}>{p}</li>)}</ul></div>
        </div>
      </div>
      <div className="card">
        <Field l="Preparer">{userName(c.preparer_id)}</Field>
        <Field l="Reviewer">{userName(c.reviewer_id)}</Field>
        <Field l="Test approach">{c.test_type.reason}</Field>
        <Field l="Expected evidence"><ul>{c.expected_evidence.map((e: string, i: number) => <li key={i}>{e}</li>)}</ul></Field>
        <Field l="Library source">{c.library_ref ?? "Custom"}</Field>
        {!locked && <button className="ghost" onClick={start}>Edit control</button>}
      </div>
    </div>
  );
}

function Field({ l, children }: any) {
  return <div className="field"><div className="field-l">{l}</div><div>{children}</div></div>;
}

// ---------------------------------------------------------------- agent runs
function useRuns(cid: number, agent: string) {
  const [runs, reload] = useLoad<any[]>(() => api.get(`/controls/${cid}/runs?agent=${agent}`), [cid, agent]);
  const [sel, setSel] = useState<number | null>(null);
  const [run, setRun] = useState<any>(null);
  const id = sel ?? runs?.[0]?.id ?? null;
  useEffect(() => {
    if (!id) { setRun(null); return; }
    let live = true; let t: any;
    const load = async () => {
      const r = await api.get(`/runs/${id}`).catch(() => null);
      if (!live || !r) return;
      setRun(r);
      if (r.status === "queued" || r.status === "running") t = setTimeout(load, 1500);
      else if (runs && runs[0]?.id === r.id && runs[0].status !== r.status) reload();
    };
    load();
    return () => { live = false; clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, runs]);
  return { runs: runs ?? [], run, select: setSel, reload: () => { setSel(null); reload(); } };
}

function AgentBar({ c, agent, title, locked, state, onDone }: any) {
  const { busy, run } = useAction();
  const active = state.run && ["queued", "running"].includes(state.run.status);
  useEffect(() => { if (state.run && !active) onDone?.(); /* eslint-disable-next-line */ }, [state.run?.status]);
  return (
    <div className="agentbar">
      <div>
        <div className="agent-name"><span className="spark">✦</span> {title}</div>
        <div className="muted small">{c.ai_provider === "mock" ? "Offline demo mode — keyword matching, no AI. Set an API key for real AI." : "Runs on your evidence only; every claim must cite it."}</div>
      </div>
      <div className="row gap">
        {state.runs.length > 0 && (
          <select value={state.run?.id ?? ""} onChange={(e) => state.select(Number(e.target.value))}>
            {state.runs.map((r: any) => <option key={r.id} value={r.id}>Run #{r.id} · {label(r.status)} · {fmtDate(r.created_at)}</option>)}
          </select>
        )}
        {!locked && <button className="primary" disabled={busy || active} onClick={async () => { if (await run(() => api.post(`/controls/${c.id}/runs`, { agent }))) state.reload(); }}>{active ? "Running…" : state.runs.length ? "Run again" : "Run agent"}</button>}
      </div>
    </div>
  );
}

function RunSteps({ run }: { run: any }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!run) return null;
  return (
    <div className="card steps">
      <div className="row between">
        <h4>Agent steps</h4>
        <div className="muted small mono">{run.model || run.provider} · {run.prompt_version} · {run.input_tokens + run.output_tokens} tokens · input {run.input_hash.slice(0, 10)}</div>
      </div>
      <ol className="timeline">
        {run.steps.map((s: any, i: number) => (
          <li key={s.key} className={s.status}>
            <button className="step-h" onClick={() => setOpen(open === s.key ? null : s.key)}>
              <span className="n">{i + 1}</span>{s.title}{s.model && <span className="muted small mono">{s.model}</span>}<Badge v={s.status === "done" ? "succeeded" : s.status} text={s.status} />
            </button>
            {s.error && <div className="errorbox">{s.error}</div>}
            {open === s.key && <pre className="json">{JSON.stringify(s.output, null, 2)}</pre>}
          </li>
        ))}
      </ol>
      {run.status === "failed" && !run.steps.some((s: any) => s.error) && <div className="errorbox">{run.error}</div>}
      {run.guardrail_flags?.length > 0 && (
        <div className="flags">
          <h4>Guardrail flags ({run.guardrail_flags.length})</h4>
          {run.guardrail_flags.map((f: any, i: number) => <div key={i} className="flag"><Badge v="medium" text={f.type.replace(/_/g, " ")} /> <span className="mono">{f.where}</span> {f.detail}</div>)}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------- DE / OE stage
function StageTab({ stage, c, locked, refresh }: any) {
  const state = useRuns(c.id, stage);
  const [xs, reloadX] = useLoad<any[]>(() => stage === "operating" ? api.get(`/controls/${c.id}/exceptions`) : Promise.resolve([]), [c.id, stage]);
  const r = state.run?.status === "succeeded" ? state.run.result : null;
  return (
    <div className="stack">
      <AgentBar c={c} agent={stage} locked={locked} state={state} onDone={() => { refresh(); reloadX(); }}
        title={stage === "design" ? "Design Effectiveness agent" : "Operating Effectiveness agent"} />
      {stage === "operating" && c.test_type && <div className="banner info"><b>Test approach:</b> {c.test_type.reason}</div>}
      {r && stage === "design" && <DesignResult r={r} c={c} />}
      {r && stage === "operating" && <OperatingResult r={r} c={c} />}
      {stage === "operating" && xs && xs.length > 0 && <Exceptions xs={xs} locked={locked} onChange={() => { reloadX(); refresh(); }} />}
      <div className="grid-side">
        <ConclusionForm stage={stage} c={c} run={state.run} locked={locked} onDone={refresh} />
        <SignOffs stage={stage} c={c} locked={locked} onDone={refresh} />
      </div>
      <RunSteps run={state.run} />
      {state.runs.length === 0 && <Empty title="Agent has not run yet">Upload evidence, then run the agent. It will draft results for you to check.</Empty>}
    </div>
  );
}

function DesignResult({ r, c }: any) {
  const ev = r.evaluation;
  const text = (id: string) => c.attributes.find((a: any) => a.id === id)?.text ?? "";
  const plan = Object.fromEntries((r.plan.attributes || []).map((p: any) => [p.attribute_id, p]));
  return (
    <div className="card">
      <div className="row between">
        <h4>Agent results by attribute</h4>
        <div className="row gap"><span className="muted small">Proposed:</span><Badge v={r.proposed_conclusion.design} text={`Design: ${label(r.proposed_conclusion.design)}`} /><Badge v={r.proposed_conclusion.implementation} text={label(r.proposed_conclusion.implementation)} /></div>
      </div>
      <p>{ev.summary}</p>
      <table className="table attrs-table">
        <thead><tr><th>Attribute</th><th>Design</th><th>Implemented</th><th>Reasoning and evidence</th></tr></thead>
        <tbody>{ev.attribute_results.map((a: any) => (
          <tr key={a.attribute_id}>
            <td><span className="mono">{a.attribute_id}</span> {text(a.attribute_id)}{plan[a.attribute_id] && <div className="muted small">{plan[a.attribute_id].addresses_risk}</div>}</td>
            <td><Badge v={a.design_assessment} />{a.downgraded && <div className="warn-text small">downgraded by guardrail</div>}</td>
            <td><Badge v={a.implemented} /></td>
            <td><div>{a.reasoning}</div><Citations list={a.citations} /></td>
          </tr>
        ))}</tbody>
      </table>
      {(ev.gaps?.length > 0 || ev.evidence_requests?.length > 0) && (
        <div className="grid2">
          {ev.gaps?.length > 0 && <div><h4>Gaps</h4><ul>{ev.gaps.map((g: string, i: number) => <li key={i}>{g}</li>)}</ul></div>}
          {ev.evidence_requests?.length > 0 && <div><h4>Evidence to request</h4><ul>{ev.evidence_requests.map((g: string, i: number) => <li key={i}>{g}</li>)}</ul></div>}
        </div>
      )}
      {r.plan.suggested_additional_attributes?.length > 0 && <div className="banner info"><b>Agent suggests adding attributes:</b> {r.plan.suggested_additional_attributes.join("; ")}</div>}
    </div>
  );
}

function OperatingResult({ r, c }: any) {
  const [cell, setCell] = useState<any>(null);
  const p = r.proposed_conclusion;
  return (
    <div className="card">
      <div className="row between">
        <h4>Test results — {p.items_tested} item(s)</h4>
        <div className="row gap"><span className="muted small">Proposed:</span><Badge v={p.operating} /><span className="small">{p.items_with_exceptions} with exceptions</span></div>
      </div>
      {r.test_plan.rationale && <p className="muted small">Sample: {r.test_plan.rationale} {r.test_plan.seed ? `(seed ${r.test_plan.seed})` : ""}</p>}
      <div className="matrix-wrap">
        <table className="table matrix">
          <thead><tr><th>#</th><th>Sample item</th>{c.attributes.map((a: any) => <th key={a.id} title={a.text}>{a.id}</th>)}</tr></thead>
          <tbody>{r.results.items.map((it: any) => (
            <tr key={it.sample_index}>
              <td className="mono">{it.sample_index}</td><td className="small">{it.label}</td>
              {c.attributes.map((a: any) => {
                const x = it.results.find((y: any) => y.attribute_id === a.id);
                return <td key={a.id}><button className={`cell ${x?.result ?? "none"}`} onClick={() => setCell({ it, x, a })}>{x ? (x.result === "pass" ? "✓" : x.result === "fail" ? "✗" : "?") : "—"}</button></td>;
              })}
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="muted small">Click a cell to see the agent's note and evidence.</div>
      {cell && (
        <Modal title={`Sample #${cell.it.sample_index} · ${cell.a.id}`} onClose={() => setCell(null)} wide>
          <p className="muted">{cell.a.text}</p>
          <p><Badge v={cell.x?.result} /> {cell.x?.note}</p>
          <Citations list={cell.x?.citations} />
        </Modal>
      )}
    </div>
  );
}

function Exceptions({ xs, locked, onChange }: any) {
  const { run } = useAction();
  return (
    <div className="card">
      <h4>Exceptions ({xs.length})</h4>
      <table className="table compact">
        <thead><tr><th>Sample item</th><th>Attr.</th><th>Description</th><th>Severity</th><th>Status</th></tr></thead>
        <tbody>{xs.map((x: any) => (
          <tr key={x.id}>
            <td className="small">{x.sample_item}</td><td className="mono">{x.attribute_id}</td><td>{x.description}</td>
            <td><select disabled={locked} value={x.severity} onChange={(e) => run(async () => { await api.patch(`/exceptions/${x.id}`, { severity: e.target.value }); onChange(); })}><option value="deficiency">Deficiency</option><option value="significant">Significant deficiency</option><option value="material">Material weakness</option></select></td>
            <td><select disabled={locked} value={x.status} onChange={(e) => run(async () => { await api.patch(`/exceptions/${x.id}`, { status: e.target.value }); onChange(); })}><option value="open">Open</option><option value="accepted">Accepted</option><option value="remediated">Remediated</option></select></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function ConclusionForm({ stage, c, run, locked, onDone }: any) {
  const current = stage === "design" ? c.design_conclusion : c.operating_conclusion;
  const proposed = run?.status === "succeeded" ? run.result?.proposed_conclusion : null;
  const keys = stage === "design" ? ["design", "implementation"] : ["operating"];
  const OPTS: Record<string, string[]> = {
    design: ["effective", "not_effective", "insufficient_evidence"],
    implementation: ["implemented", "not_implemented", "insufficient_evidence"],
    operating: ["operating_effectively", "not_operating_effectively", "insufficient_evidence"],
  };
  const init = () => Object.fromEntries(keys.map((k) => [k, current?.[k] ?? proposed?.[k] ?? OPTS[k][0]]));
  const [v, setV] = useState<any>(init);
  const [why, setWhy] = useState(current?.rationale ?? "");
  useEffect(() => { setV(init()); setWhy(current?.rationale ?? ""); /* eslint-disable-next-line */ }, [run?.id, run?.status, current?.confirmed_by, current?.run_id]);
  const { busy, run: act } = useAction();
  const override = proposed && keys.some((k) => proposed[k] !== v[k]);
  return (
    <div className="card form">
      <h4>Your conclusion</h4>
      <p className="muted small">The agent proposes; you decide. If you differ from the agent, say why.</p>
      {keys.map((k) => (
        <label key={k}>{k === "operating" ? "Operating effectiveness" : k === "design" ? "Design" : "Implementation"}
          <select disabled={locked} value={v[k]} onChange={(e) => setV({ ...v, [k]: e.target.value })}>{OPTS[k].map((o) => <option key={o} value={o}>{label(o)}{proposed?.[k] === o ? " (agent)" : ""}</option>)}</select>
        </label>
      ))}
      <label>Rationale {override && <span className="warn-text small">required — you changed the agent's proposal</span>}
        <textarea disabled={locked} rows={3} value={why} onChange={(e) => setWhy(e.target.value)} placeholder="Basis for the conclusion, referencing evidence IDs" />
      </label>
      {current && <div className="muted small">Confirmed by {current.confirmed_by}{current.overrode_agent ? " (overrode agent)" : ""}{current.run_id ? ` from run #${current.run_id}` : ""}</div>}
      {!locked && <button className="primary" disabled={busy} onClick={async () => {
        if (await act(() => api.post(`/controls/${c.id}/conclusion`, { stage, run_id: proposed ? run.id : null, conclusion: v, rationale: why }), "Conclusion confirmed")) onDone();
      }}>Confirm conclusion</button>}
    </div>
  );
}

function SignOffs({ stage, c, locked, onDone }: any) {
  const user = useUser();
  const [comment, setComment] = useState("");
  const { busy, run } = useAction();
  const list = c.signoffs.filter((s: any) => s.stage === stage);
  const canPrepare = c.status === `${stage}_in_progress`;
  const canReview = c.status === `${stage}_prepared` && can(user, "reviewer");
  return (
    <div className="card form">
      <h4>Sign-offs</h4>
      {list.length === 0 && <p className="muted small">No sign-offs yet.</p>}
      {list.map((s: any) => (
        <div key={s.id} className={`signoff ${s.revoked ? "revoked" : ""}`}>
          <Badge v={s.revoked ? "low" : "succeeded"} text={s.revoked ? `${s.kind} (revoked)` : s.kind === "prepare" ? "Prepared" : "Reviewed"} />
          <span>{s.user.name}</span><span className="muted small">{fmtDate(s.at)}</span>
          {s.comment && <div className="muted small">“{s.comment}”</div>}
        </div>
      ))}
      {!locked && (canPrepare || canReview) && (
        <>
          <input placeholder="Comment (optional)" value={comment} onChange={(e) => setComment(e.target.value)} />
          {canPrepare && <button className="primary" disabled={busy} onClick={async () => { if (await run(() => api.post(`/controls/${c.id}/signoffs`, { stage, kind: "prepare", comment }), "Signed off as preparer")) { setComment(""); onDone(); } }}>Sign off as preparer</button>}
          {canReview && <button className="primary" disabled={busy} onClick={async () => { if (await run(() => api.post(`/controls/${c.id}/signoffs`, { stage, kind: "review", comment }), "Signed off as reviewer")) { setComment(""); onDone(); } }}>Sign off as reviewer</button>}
        </>
      )}
      <p className="muted small">The person who prepares cannot review. Changes to the control or its evidence revoke sign-offs.</p>
    </div>
  );
}

// ------------------------------------------------------------------ sampling
function SamplingTab({ c, evidence, locked, refresh }: any) {
  const user = useUser();
  const [info, reload] = useLoad<any>(() => api.get(`/controls/${c.id}/sampling`), [c.id]);
  const pops = evidence.filter((e: any) => e.purpose === "population");
  const [pop, setPop] = useState<string>("");
  const [seed, setSeed] = useState("");
  const [ov, setOv] = useState("");
  const [why, setWhy] = useState("");
  const { busy, run } = useAction();
  if (!info) return <Loading />;
  const s = info.sample;
  return (
    <div className="stack">
      <div className="grid-side">
        <div className="card">
          <h4>Methodology</h4>
          <Field l="Test type">{info.test_type.test_type === "sampling" ? "Sampling" : "Non-sampling (test of one)"}</Field>
          <Field l="Why">{info.test_type.reason}</Field>
          <Field l="Methodology sample size">{info.suggested_size} — {info.basis}</Field>
          <p className="muted small">Sample sizes are calculated by the platform, not by AI, so they are repeatable. A recorded seed lets anyone re-create the same selection.</p>
        </div>
        {!locked && (
          <div className="card form">
            <h4>Select sample</h4>
            <label>Population file
              <select value={pop} onChange={(e) => setPop(e.target.value)}>
                <option value="">{info.test_type.method === "test_of_one" ? "None (test of one)" : "Choose…"}</option>
                {pops.map((p: any) => <option key={p.id} value={p.id}>{p.label} · {p.filename}</option>)}
              </select>
            </label>
            {pops.length === 0 && <div className="muted small">Upload the population (CSV or Excel with a header row) on the Evidence tab with purpose “Population”.</div>}
            <label>Seed (optional)<input value={seed} onChange={(e) => setSeed(e.target.value.replace(/\D/g, ""))} placeholder="random if blank" /></label>
            <details><summary className="small">Override sample size</summary>
              <label>Sample size<input value={ov} onChange={(e) => setOv(e.target.value.replace(/\D/g, ""))} /></label>
              <label>Reason<input value={why} onChange={(e) => setWhy(e.target.value)} /></label>
              {!can(user, "reviewer") && <div className="muted small">Going below methodology needs reviewer role.</div>}
            </details>
            <button className="primary" disabled={busy} onClick={async () => {
              const body: any = { population_evidence_id: pop ? Number(pop) : null };
              if (seed) body.seed = Number(seed);
              if (ov) { body.override_size = Number(ov); body.override_reason = why; }
              if (await run(() => api.post(`/controls/${c.id}/sampling`, body), "Sample selected")) { reload(); refresh(); }
            }}>{s ? "Re-select sample" : "Select sample"}</button>
          </div>
        )}
      </div>
      {s ? (
        <div className="card">
          <div className="row between"><h4>Current sample — {s.sample_size} of {s.population_size}</h4><span className="muted small mono">method {s.method} · seed {s.seed} · {fmtDate(s.created_at)}</span></div>
          <p className="muted small">{s.rationale}</p>
          <div className="matrix-wrap">
            <table className="table compact">
              <thead><tr><th>Pop. row</th>{Object.keys(s.items[0]?.row ?? {}).map((k) => <th key={k}>{k}</th>)}</tr></thead>
              <tbody>{s.items.map((it: any) => <tr key={it.index}><td className="mono">{it.index}</td>{Object.values(it.row).map((v: any, i) => <td key={i}>{String(v)}</td>)}</tr>)}</tbody>
            </table>
          </div>
        </div>
      ) : <Empty title="No sample selected yet" />}
    </div>
  );
}

// -------------------------------------------------------------------- review
function ReviewTab({ c, notes, locked, refresh }: any) {
  const user = useUser();
  const state = useRuns(c.id, "reviewer");
  const [f, setF] = useState({ stage: "design", severity: "medium", text: "" });
  const [reply, setReply] = useState<Record<number, string>>({});
  const { busy, run } = useAction();
  const r = state.run?.status === "succeeded" ? state.run.result : null;
  return (
    <div className="stack">
      <AgentBar c={c} agent="reviewer" title="Reviewer agent" locked={locked} state={state} onDone={refresh} />
      {r?.overall && <div className="banner info"><b>Reviewer agent summary:</b> {r.overall}</div>}
      {!locked && (
        <form className="card upload" onSubmit={async (e) => { e.preventDefault(); if (await run(() => api.post(`/controls/${c.id}/notes`, f), "Note added")) { setF({ ...f, text: "" }); refresh(); } }}>
          <select value={f.stage} onChange={(e) => setF({ ...f, stage: e.target.value })}><option value="design">DE</option><option value="operating">OE</option></select>
          <select value={f.severity} onChange={(e) => setF({ ...f, severity: e.target.value })}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select>
          <input className="grow" placeholder="Write a review note…" value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} required />
          <button className="primary" disabled={busy}>Add note</button>
        </form>
      )}
      {notes.length === 0 ? <Empty title="No review notes" /> : notes.map((n: any) => (
        <div key={n.id} className={`card note ${n.status}`}>
          <div className="row between">
            <div className="row gap"><Badge v={n.severity} /><Badge v="low" text={n.stage === "design" ? "DE" : "OE"} />{n.source === "reviewer_agent" && <span className="small muted">✦ Reviewer agent</span>}</div>
            <div className="row gap"><Badge v={n.status} /><span className="muted small">{fmtDate(n.created_at)}</span></div>
          </div>
          <p>{n.text}</p>
          {n.response && <div className="response"><b>Response:</b> {n.response}</div>}
          {!locked && n.status !== "closed" && (
            <div className="row gap">
              <input className="grow" placeholder="Respond…" value={reply[n.id] ?? ""} onChange={(e) => setReply({ ...reply, [n.id]: e.target.value })} />
              <button className="ghost sm" onClick={() => run(async () => { await api.patch(`/notes/${n.id}`, { response: reply[n.id] ?? n.response, status: "addressed" }); refresh(); }, "Marked addressed")}>Mark addressed</button>
              {can(user, "reviewer") && <button className="ghost sm" onClick={() => run(async () => { await api.patch(`/notes/${n.id}`, { status: "closed" }); refresh(); }, "Note closed")}>Close</button>}
            </div>
          )}
        </div>
      ))}
      <RunSteps run={state.run} />
    </div>
  );
}
