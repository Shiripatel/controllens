import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, fmtDate, label } from "../api";
import { can, useUser } from "../App";
import { Badge, Empty, ErrorBox, Loading, Modal, Tabs, useAction, useLoad } from "../components/ui";
import { Activity } from "./Engagement";
import { Citations, EvidenceBody, EvidenceDock, EvidenceTab, RequestsTab } from "./Extras";

const FLOW = [
  ["not_started", "Not started"], ["design_in_progress", "Design"], ["design_prepared", "Design prepared"], ["design_reviewed", "Design reviewed"],
  ["operating_in_progress", "Operating"], ["operating_prepared", "Operating prepared"], ["operating_reviewed", "Complete"],
];

const AGENTS = [
  { key: "design", name: "Design Effectiveness", desc: "Checks that the control is designed well for the risk and was actually put in place.", needs: "Policy, procedure and walkthrough evidence" },
  { key: "operating", name: "Operating Effectiveness", desc: "Tests every sample item against every attribute and logs exceptions.", needs: "A selected sample and the test evidence" },
  { key: "reviewer", name: "Reviewer", desc: "Runs quality checks on the work and raises review notes.", needs: "At least one finished agent run" },
];

// ---------------------------------------------------------------- workspace
// Three panes: control details (left) · work area (centre) · agent runs (right)
export default function ControlWorkspace() {
  const { cid } = useParams();
  const [railTick, setRailTick] = useState(0);
  const [centerKey, setCenterKey] = useState(0);
  const [c, reload, err] = useLoad<any>(() => api.get(`/controls/${cid}`), [cid]);
  const [evidence, reloadEv] = useLoad<any[]>(() => api.get(`/controls/${cid}/evidence`), [cid]);
  const [notes, reloadNotes] = useLoad<any[]>(() => api.get(`/controls/${cid}/notes`), [cid]);
  const [tab, setTab] = useState("agents");
  const [agent, setAgent] = useState<string | null>(null);
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [viewing, setViewing] = useState<{ id: number; excerpt?: string } | null>(null);
  const user = useUser();
  useEffect(() => { setTab("agents"); setAgent(null); setViewing(null); }, [cid]);
  if (err) return <ErrorBox msg={err} />;
  if (!c || !evidence || !notes || String(c.id) !== cid) return <Loading />;
  const idx = FLOW.findIndex(([k]) => k === c.status);
  const locked = c.engagement.status !== "active";
  const openNotes = notes.filter((n) => n.status !== "closed").length;
  const refresh = () => { reload(); reloadEv(); reloadNotes(); setRailTick((t) => t + 1); };
  const bumpRail = () => setRailTick((t) => t + 1);
  const openAgent = (k: string) => { if (k === "reviewer") { setTab("review"); } else { setTab("agents"); setAgent(k); } };
  const props = { c, evidence, notes, locked, refresh, onStarted: bumpRail };
  const startAgent = async (k: string) => {
    try { await api.post(`/controls/${c.id}/runs`, { agent: k }); openAgent(k); setCenterKey((x) => x + 1); bumpRail(); } catch { openAgent(k); }
  };
  const showLeft = leftOpen && !viewing;
  return (
    <EvidenceDock.Provider value={setViewing}>
    <div className="page ws-page">
      <div className="ws-head">
        <div>
          <div className="crumbs"><Link to="/engagements">Engagements</Link> / <Link to={`/engagements/${c.engagement.id}`}>{c.engagement.client} — {c.engagement.name}</Link> / {c.ref}</div>
          <div className="row gap"><span className="mono ref">{c.ref}</span><h1>{c.title}</h1><Badge v={c.status} /></div>
        </div>
        <div className="row gap">
          <button className="ghost" onClick={() => api.download(`/controls/${c.id}/workpaper.html`, `${c.ref}_workpaper.html`)}>Export work paper</button>
          <ControlNav c={c} />
        </div>
      </div>
      {locked && <div className="banner warn">Engagement is {c.engagement.status}; this control is read-only.</div>}
      <NextStep c={c} evidence={evidence} notes={notes} user={user} locked={locked} tick={railTick}
        goTab={(t: string) => { setTab(t); setAgent(null); }} openAgent={openAgent} startAgent={startAgent} />
      <div className="stepper">
        {FLOW.map(([k, l], i) => <div key={k} className={`st ${i < idx ? "done" : i === idx ? "now" : ""}`}><span className="dot" />{l}</div>)}
      </div>

      <div className={`ws ${showLeft ? "" : "no-left"} ${viewing ? "viewing" : rightOpen ? "" : "no-right"}`}>
        {showLeft
          ? <DetailsPane c={c} locked={locked} refresh={refresh} onCollapse={() => setLeftOpen(false)} />
          : <button className="pane-tab" onClick={() => setLeftOpen(true)} title="Show control details">▸<span>Control details</span></button>}

        <section className="ws-center">
          <Tabs active={tab} onChange={(t) => { setTab(t); if (t !== "agents") setAgent(null); }} tabs={[
            { key: "agents", label: "Agents" },
            { key: "evidence", label: "Evidence", count: evidence.length },
            { key: "requests", label: "Requests" },
            { key: "sampling", label: "Sampling" },
            { key: "review", label: "Review notes", count: openNotes },
            { key: "activity", label: "Activity" },
          ]} />
          {tab === "agents" && !agent && <Launcher c={c} evidence={evidence} onOpen={openAgent} />}
          {tab === "agents" && agent && (
            <>
              <button className="back" onClick={() => setAgent(null)}>← All agents</button>
              <StageTab key={`${agent}-${centerKey}`} stage={agent} {...props} />
            </>
          )}
          {tab === "evidence" && <EvidenceTab {...props} />}
          {tab === "requests" && <RequestsTab {...props} />}
          {tab === "sampling" && <SamplingTab {...props} />}
          {tab === "review" && <ReviewTab key={`rev-${centerKey}`} {...props} />}
          {tab === "activity" && <Activity path={`/controls/${cid}/activity`} />}
        </section>

        {viewing ? (
          <aside className="pane evpane">
            <div className="pane-head"><b>Evidence E{viewing.id}</b><button className="icon" onClick={() => setViewing(null)} title="Close evidence">×</button></div>
            <div className="pane-body"><EvidenceBody key={`${viewing.id}-${viewing.excerpt}`} id={viewing.id} excerpt={viewing.excerpt} /></div>
          </aside>
        ) : rightOpen
          ? <AgentRail c={c} locked={locked} tick={railTick} current={tab === "review" ? "reviewer" : agent} onOpen={openAgent}
              onStarted={(k: string) => { openAgent(k); setCenterKey((x) => x + 1); bumpRail(); }} onFinished={refresh} onCollapse={() => setRightOpen(false)} />
          : <button className="pane-tab right" onClick={() => setRightOpen(true)} title="Show agents">◂<span>Agents</span></button>}
      </div>
    </div>
    </EvidenceDock.Provider>
  );
}

// ----------------------------------------------------------------- next step
/** One line that says what to do next on this control, with a button to do it. */
function NextStep({ c, evidence, notes, user, locked, tick, goTab, openAgent, startAgent }: any) {
  const [runs] = useLoad<any[]>(() => api.get(`/controls/${c.id}/runs`), [c.id, tick]);
  const [samp] = useLoad<any>(() => api.get(`/controls/${c.id}/sampling`), [c.id, tick]);
  if (!runs || !samp || locked) return null;
  const ok = (a: string) => runs.some((r) => r.agent === a && r.status === "succeeded");
  const busy = runs.find((r) => ["queued", "running"].includes(r.status));
  const openN = (st: string) => notes.filter((n: any) => n.stage === st && n.status !== "closed").length;
  const iPrepared = (st: string) => c.signoffs.some((s: any) => s.stage === st && s.kind === "prepare" && !s.revoked && s.user.id === user.id);
  const stage = c.status.startsWith("operating") || c.status === "design_reviewed" ? "operating" : "design";
  const name = stage === "design" ? "Design Effectiveness" : "Operating Effectiveness";
  let text = "", btn = "", act: (() => void) | null = null, done = false;
  if (busy) { text = "An agent is running. Results will show when it finishes."; }
  else if (c.status === "operating_reviewed") { text = "This control is complete."; btn = "Export work paper"; act = () => api.download(`/controls/${c.id}/workpaper.html`, `${c.ref}_workpaper.html`); done = true; }
  else if (c.status.endsWith("_prepared")) {
    const n = openN(stage);
    if (n) { text = `${n} review note(s) need to be answered and closed before review sign-off.`; btn = "Open review notes"; act = () => goTab("review"); }
    else if (can(user, "reviewer") && !iPrepared(stage)) { text = `Review the ${stage} work and sign off as reviewer.`; btn = "Open to review"; act = () => openAgent(stage); }
    else { text = "Waiting for the reviewer to sign off. You can run the Reviewer agent to pre-check the work."; btn = "Open review notes"; act = () => goTab("review"); }
  }
  else if (stage === "design" && !evidence.some((e: any) => e.purpose !== "population")) { text = "Upload the design evidence: policy, procedure or walkthrough."; btn = "Go to evidence"; act = () => goTab("evidence"); }
  else if (stage === "operating" && samp.test_type.test_type === "sampling" && !samp.sample) { text = "Select the sample to test."; btn = "Go to sampling"; act = () => goTab("sampling"); }
  else if (!ok(stage)) { text = `Run the ${name} agent.`; btn = "Run agent"; act = () => startAgent(stage); }
  else if (!(stage === "design" ? c.design_conclusion : c.operating_conclusion)) { text = "Check the agent's results, then confirm your conclusion."; btn = "Open results"; act = () => openAgent(stage); }
  else { text = `Sign off the ${stage} work as preparer.`; btn = "Open to sign off"; act = () => openAgent(stage); }
  return (
    <div className={`nextstep ${done ? "done" : ""}`}>
      <span className="nextstep-l">{done ? "Done" : "Next step"}</span>
      <span className="nextstep-t">{text}</span>
      {btn && <button className={done ? "ghost sm" : "primary sm"} onClick={() => act?.()}>{btn}</button>}
    </div>
  );
}

function ControlNav({ c }: any) {
  const nav = useNavigate();
  const [list] = useLoad<any[]>(() => api.get(`/engagements/${c.engagement.id}/controls`), [c.engagement.id]);
  const i = list?.findIndex((x) => x.id === c.id) ?? -1;
  const go = (d: number) => list && list[i + d] && nav(`/controls/${list[i + d].id}`);
  return (
    <div className="row navbtns">
      <button className="ghost" disabled={i <= 0} onClick={() => go(-1)} title="Previous control">‹</button>
      <span className="muted small">{i >= 0 ? `${i + 1} of ${list!.length}` : ""}</span>
      <button className="ghost" disabled={!list || i >= list.length - 1} onClick={() => go(1)} title="Next control">›</button>
    </div>
  );
}

// ------------------------------------------------------------- left: details
const EDITABLE = ["title", "description", "objective", "risk", "frequency", "nature", "risk_rating", "key_control", "system_id",
  "attributes", "design_procedures", "operating_procedures", "preparer_id", "reviewer_id"];
const pick = (c: any) => Object.fromEntries(EDITABLE.map((k) => [k, c[k]]));

function DetailsPane({ c, locked, refresh, onCollapse }: any) {
  const [f, setF] = useState<any>(() => pick(c));
  const [users] = useLoad<any[]>(() => api.get("/users"), []);
  const [eng] = useLoad<any>(() => api.get(`/engagements/${c.engagement.id}`), [c.engagement.id]);
  const { busy, run } = useAction();
  const changed = EDITABLE.filter((k) => JSON.stringify(f[k]) !== JSON.stringify(c[k]));
  const dirty = changed.length > 0;
  const dirtyRef = useRef(dirty); dirtyRef.current = dirty;
  useEffect(() => { if (!dirtyRef.current) setF(pick(c)); /* eslint-disable-next-line */ }, [c.row_version, c.id]);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const lines = (k: string) => ({ value: (f[k] || []).join("\n"), onChange: (e: any) => setF({ ...f, [k]: e.target.value.split("\n") }) });
  const signs = (stage: string, kind: string) => c.signoffs.filter((s: any) => s.stage === stage && s.kind === kind && !s.revoked);
  const SignRow = ({ stage, name }: { stage: string; name: string }) => (
    <div className="signrow">
      <span className="field-l">{name}</span>
      {["prepare", "review"].map((k) => {
        const s = signs(stage, k)[0];
        return <span key={k} className={`signchip ${s ? "on" : ""}`} title={s ? `${s.user.name} · ${fmtDate(s.at)}` : "Not signed"}>{s ? "✓" : "○"} {k === "prepare" ? "Prepared" : "Reviewed"}{s ? ` · ${s.user.name.split(" ")[0]}` : ""}</span>;
      })}
    </div>
  );
  return (
    <aside className="pane">
      <div className="pane-head"><b>Control details</b><button className="icon" onClick={onCollapse} title="Hide">«</button></div>
      <div className="pane-body form">
        <div className="signbox">
          <SignRow stage="design" name="Design" />
          <SignRow stage="operating" name="Operating" />
          <div className="row gap">
            {c.design_conclusion && <Badge v={c.design_conclusion.design} text={`Design: ${label(c.design_conclusion.design)}`} />}
            {c.operating_conclusion && <Badge v={c.operating_conclusion.operating} />}
          </div>
        </div>
        <fieldset disabled={locked}>
          <label>Control title<input value={f.title} onChange={set("title")} /></label>
          <label>Control description<textarea rows={4} value={f.description} onChange={set("description")} /></label>
          <label>Risk addressed<textarea rows={3} value={f.risk} onChange={set("risk")} /></label>
          <label>Control objective<textarea rows={2} value={f.objective} onChange={set("objective")} /></label>
          <label>System / IT layer
            <select value={f.system_id ?? ""} onChange={(e) => setF({ ...f, system_id: e.target.value ? Number(e.target.value) : null })}>
              <option value="">Not set</option>
              {eng?.systems.map((s: any) => <option key={s.id} value={s.id}>{s.name} ({s.layer})</option>)}
            </select>
          </label>
          <div className="grid2 tight">
            <label>Nature<select value={f.nature} onChange={set("nature")}>{["Manual", "IT-dependent manual", "Automated"].map((x) => <option key={x}>{x}</option>)}</select></label>
            <label>Frequency<select value={f.frequency} onChange={set("frequency")}>{["Annual", "Quarterly", "Monthly", "Weekly", "Daily", "Multiple times per day", "Event-driven", "Continuous (automated)"].map((x) => <option key={x}>{x}</option>)}</select></label>
            <label>Risk rating<select value={f.risk_rating} onChange={set("risk_rating")}>{["Low", "Moderate", "High"].map((x) => <option key={x}>{x}</option>)}</select></label>
            <label className="check keyc"><input type="checkbox" checked={!!f.key_control} onChange={(e) => setF({ ...f, key_control: e.target.checked })} /> Key control</label>
          </div>
          <div className="field-l">Control attributes</div>
          {f.attributes.map((a: any, i: number) => (
            <div key={i} className="attr-row">
              <span className="mono">{a.id}</span>
              <textarea rows={3} value={a.text} onChange={(e) => { const x = [...f.attributes]; x[i] = { ...a, text: e.target.value }; setF({ ...f, attributes: x }); }} />
              <button type="button" className="icon" title="Remove attribute" onClick={() => setF({ ...f, attributes: f.attributes.filter((_: any, j: number) => j !== i) })}>×</button>
            </div>
          ))}
          <button type="button" className="ghost sm" onClick={() => {
            const n = Math.max(0, ...f.attributes.map((a: any) => Number(String(a.id).slice(1)) || 0)) + 1;
            setF({ ...f, attributes: [...f.attributes, { id: `A${n}`, text: "" }] });
          }}>+ Add attribute</button>
          <label>Design procedures <span className="muted small">one per line</span><textarea rows={4} {...lines("design_procedures")} /></label>
          <label>Operating test procedures <span className="muted small">one per line</span><textarea rows={4} {...lines("operating_procedures")} /></label>
          <div className="grid2 tight">
            <label>Preparer<select value={f.preparer_id ?? ""} onChange={(e) => setF({ ...f, preparer_id: e.target.value ? Number(e.target.value) : null })}><option value="">—</option>{users?.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></label>
            <label>Reviewer<select value={f.reviewer_id ?? ""} onChange={(e) => setF({ ...f, reviewer_id: e.target.value ? Number(e.target.value) : null })}><option value="">—</option>{users?.filter((u) => ["reviewer", "manager", "admin"].includes(u.role)).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></label>
          </div>
        </fieldset>
        <Field l="Test approach">{c.test_type.reason}</Field>
        <Field l="Evidence to request"><ul>{c.expected_evidence.map((e: string, i: number) => <li key={i}>{e}</li>)}</ul></Field>
        <div className="muted small">Source: {c.library_ref ? `library ${c.library_ref}` : "custom control"}</div>
      </div>
      {dirty && !locked && (
        <div className="pane-foot">
          <div className="muted small">Unsaved changes. Changing the control itself resets its sign-offs.</div>
          <div className="row gap">
            <button className="ghost sm" onClick={() => setF(pick(c))}>Discard</button>
            <button className="primary sm" disabled={busy} onClick={async () => {
              const body: any = { row_version: c.row_version };
              changed.forEach((k) => { body[k] = k.endsWith("_procedures") ? f[k].map((x: string) => x.trim()).filter(Boolean) : f[k]; });
              if (await run(() => api.patch(`/controls/${c.id}`, body), "Control saved")) { dirtyRef.current = false; setF(pick({ ...c, ...body })); refresh(); }
            }}>Save</button>
          </div>
        </div>
      )}
    </aside>
  );
}

function Field({ l, children }: any) {
  return <div className="field"><div className="field-l">{l}</div><div>{children}</div></div>;
}

// ----------------------------------------------------------- centre: launcher
function Launcher({ c, evidence, onOpen }: any) {
  const ready: Record<string, [boolean, string]> = {
    design: [evidence.some((e: any) => e.purpose !== "population"), evidence.length ? `${evidence.length} evidence file(s) attached` : "No evidence uploaded yet"],
    operating: [["design_reviewed", "operating_in_progress", "operating_prepared", "operating_reviewed"].includes(c.status), ["not_started", "design_in_progress", "design_prepared"].includes(c.status) ? "Design is not reviewed yet" : "Design is reviewed"],
    reviewer: [c.status !== "not_started", c.status === "not_started" ? "No work to review yet" : "Work is ready to check"],
  };
  return (
    <div className="launcher">
      <div className="launcher-h"><span className="spark dark">✦</span> Agents<div className="muted small">Pick an agent to start work on this control. Agents draft; you decide and sign off.</div></div>
      {AGENTS.map((a, i) => (
        <button key={a.key} className="launch" onClick={() => onOpen(a.key)}>
          <span className="launch-n">{i + 1}</span>
          <span className="launch-t"><b>{a.name}</b><span className="muted small">{a.desc}</span>
            <span className={`small ${ready[a.key][0] ? "good-text" : "warn-text"}`}>{ready[a.key][0] ? "●" : "○"} {ready[a.key][1]}</span></span>
          <span className="launch-go">Open →</span>
        </button>
      ))}
    </div>
  );
}

function LiveSteps({ id }: { id: number }) {
  const [run, setRun] = useState<any>(null);
  useEffect(() => {
    let live = true; let t: any;
    const load = async () => { const x = await api.get(`/runs/${id}`).catch(() => null); if (!live) return; if (x) setRun(x); t = setTimeout(load, 1200); };
    load();
    return () => { live = false; clearTimeout(t); };
  }, [id]);
  if (!run?.steps?.length) return <div className="muted small">Starting…</div>;
  return <ol className="live">{run.steps.map((s: any) => <li key={s.key} className={s.status}>{s.status === "done" ? "✓" : s.status === "failed" ? "✗" : "…"} {s.title}</li>)}</ol>;
}

// -------------------------------------------------------- right: agent runs
function AgentRail({ c, locked, tick, current, onOpen, onStarted, onFinished, onCollapse }: any) {
  const [runs, reload] = useLoad<any[]>(() => api.get(`/controls/${c.id}/runs`), [c.id, tick]);
  const { busy, run } = useAction();
  const active = !!runs?.some((r) => ["queued", "running"].includes(r.status));
  const was = useRef(false);
  useEffect(() => {
    if (active) { was.current = true; const t = setTimeout(reload, 2000); return () => clearTimeout(t); }
    if (was.current) { was.current = false; onFinished(); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, runs]);
  return (
    <aside className="pane">
      <div className="pane-head"><b><span className="spark dark">✦</span> Agents</b><button className="icon" onClick={onCollapse} title="Hide">»</button></div>
      <div className="pane-body">
        {AGENTS.map((a) => {
          const mine = (runs ?? []).filter((r) => r.agent === a.key);
          const last = mine[0];
          const running = last && ["queued", "running"].includes(last.status);
          return (
            <div key={a.key} className={`railcard ${current === a.key ? "on" : ""}`}>
              <div className="row between">
                <button className="railname" onClick={() => onOpen(a.key)}>{a.name}</button>
                {!locked && <button className="play" disabled={busy || running} title={last ? "Run again" : "Run agent"}
                  onClick={async () => { if (await run(() => api.post(`/controls/${c.id}/runs`, { agent: a.key }))) onStarted(a.key); }}>{running ? "…" : "▶"}</button>}
              </div>
              <div className="railstat">
                {!last ? <><span className="dot0" /> Not run<div className="muted small">Needs: {a.needs}</div></> : (
                  <>
                    <Badge v={last.status} text={running ? "Running" : last.status === "succeeded" ? "Finished" : "Failed"} />
                    {running && <LiveSteps id={last.id} />}
                    <div className="muted small">Run #{last.id} · {fmtDate(last.created_at)}</div>
                    <div className="muted small mono">{last.model || last.provider}</div>
                    {last.flags > 0 && <div className="warn-text small">{last.flags} guardrail flag(s)</div>}
                    {last.status === "failed" && <div className="bad-text small">{last.error}</div>}
                    {mine.length > 1 && <div className="muted small">{mine.length} runs in total</div>}
                  </>
                )}
              </div>
            </div>
          );
        })}
        <div className="muted small">Every run is saved with its model, inputs and steps.</div>
      </div>
    </aside>
  );
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

function AgentBar({ c, agent, title, locked, state, onDone, onStarted }: any) {
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
        {!locked && <button className="primary" disabled={busy || active} onClick={async () => { if (await run(() => api.post(`/controls/${c.id}/runs`, { agent }))) { state.reload(); onStarted?.(); } }}>{active ? "Running…" : state.runs.length ? "Run again" : "Run agent"}</button>}
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
function StageTab({ stage, c, locked, refresh, onStarted }: any) {
  const state = useRuns(c.id, stage);
  const [xs, reloadX] = useLoad<any[]>(() => stage === "operating" ? api.get(`/controls/${c.id}/exceptions`) : Promise.resolve([]), [c.id, stage]);
  const r = state.run?.status === "succeeded" ? state.run.result : null;
  return (
    <div className="stack">
      <AgentBar c={c} agent={stage} locked={locked} state={state} onStarted={onStarted} onDone={() => { refresh(); reloadX(); }}
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
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const text = (id: string) => c.attributes.find((a: any) => a.id === id)?.text ?? "";
  const all = ev.attribute_results.every((a: any) => open[a.attribute_id]);
  return (
    <div className="card">
      <div className="row between">
        <h4>Results by attribute</h4>
        <div className="row gap"><span className="muted small">Agent proposes</span><Badge v={r.proposed_conclusion.design} text={`Design: ${label(r.proposed_conclusion.design)}`} /><Badge v={r.proposed_conclusion.implementation} text={label(r.proposed_conclusion.implementation)} /></div>
      </div>
      <p className="muted">{ev.summary}</p>
      <div className="res-head"><span>Attribute</span><span>Design</span><span>In place</span><span>
        <button className="linkbtn" onClick={() => setOpen(all ? {} : Object.fromEntries(ev.attribute_results.map((a: any) => [a.attribute_id, true])))}>{all ? "Collapse all" : "Expand all"}</button></span></div>
      {ev.attribute_results.map((a: any) => {
        const on = !!open[a.attribute_id];
        return (
          <div key={a.attribute_id} className={`res ${on ? "open" : ""}`}>
            <button className="res-row" aria-expanded={on} onClick={() => setOpen({ ...open, [a.attribute_id]: !on })}>
              <span><b>{a.attribute_id}</b> {text(a.attribute_id)}{!on && <span className="res-why">{a.reasoning}</span>}</span>
              <span><Badge v={a.design_assessment} /></span>
              <span><Badge v={a.implemented} /></span>
              <span className="muted small">{a.citations?.length || 0} quote(s) <span className="chev">{on ? "▴" : "▾"}</span></span>
            </button>
            {on && (
              <div className="res-detail">
                {a.downgraded && <div className="warn-text small">Lowered by the citation check: the quote could not be verified.</div>}
                <div>{a.reasoning}</div>
                <Citations list={a.citations} />
              </div>
            )}
          </div>
        );
      })}
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
function ReviewTab({ c, notes, locked, refresh, onStarted }: any) {
  const user = useUser();
  const state = useRuns(c.id, "reviewer");
  const [f, setF] = useState({ stage: "design", severity: "medium", text: "" });
  const [reply, setReply] = useState<Record<number, string>>({});
  const { busy, run } = useAction();
  const r = state.run?.status === "succeeded" ? state.run.result : null;
  return (
    <div className="stack">
      <AgentBar c={c} agent="reviewer" title="Reviewer agent" locked={locked} state={state} onStarted={onStarted} onDone={refresh} />
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
