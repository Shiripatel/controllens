"""Printable work paper for one control: a single self-contained HTML file."""
from datetime import datetime, timezone
from html import escape as h

from sqlalchemy.orm import Session

from .models import (AgentRun, Control, Evidence, Exception_, ReviewNote, Sample, SignOff, User)

LABEL = {
    "effective": "Effective", "not_effective": "Not effective", "insufficient_evidence": "Needs more evidence",
    "implemented": "Implemented", "not_implemented": "Not implemented",
    "operating_effectively": "Operating effectively", "not_operating_effectively": "Not operating effectively",
    "adequate": "Adequate", "inadequate": "Inadequate", "unable_to_assess": "Unable to assess",
    "yes": "Yes", "no": "No", "pass": "Pass", "fail": "Fail",
}
CSS = """
body{font:13px/1.5 -apple-system,Segoe UI,Arial,sans-serif;color:#17201c;max-width:1000px;margin:24px auto;padding:0 20px}
h1{font-size:20px;margin:0}h2{font-size:14px;margin:26px 0 8px;padding-bottom:4px;border-bottom:2px solid #0f5c4d;color:#0f5c4d;text-transform:uppercase;letter-spacing:.05em}
table{border-collapse:collapse;width:100%;margin:6px 0}th,td{border:1px solid #d5dad6;padding:5px 8px;text-align:left;vertical-align:top;overflow-wrap:anywhere}
th{background:#f3f5f2;font-size:11px;text-transform:uppercase}.muted{color:#6b756f}.mono{font-family:ui-monospace,Menlo,monospace;font-size:11.5px}
.pass{background:#e5f3ea;color:#1d7a4c}.fail{background:#fbe9e7;color:#b3261e}.unable_to_assess{background:#fdf3e0;color:#9a6200}
.cell{text-align:center;font-weight:700}.cite{font-size:12px;border-left:3px solid #d5dad6;padding-left:8px;margin:3px 0}
.box{border:1px solid #d5dad6;border-radius:6px;padding:10px 12px;margin:6px 0}.kv td:first-child{width:190px;background:#f3f5f2;font-weight:600}
.banner{background:#fdf3e0;color:#9a6200;padding:8px 12px;border-radius:6px;margin:8px 0}
@media print{body{margin:0}h2{break-after:avoid}table{break-inside:auto}tr{break-inside:avoid}}
"""


def _l(v):
    return h(LABEL.get(v, str(v).replace("_", " "))) if v else "—"


def _cites(cits):
    out = []
    for c in cits or []:
        mark = {True: "✓ verified", False: "✗ NOT found in file", None: "? check by eye"}[c.get("verified")]
        out.append(f'<div class="cite"><span class="mono">{h(str(c.get("evidence_id")))}</span> '
                   f'{h(c.get("locator") or "")} “{h(c.get("excerpt") or "")}” <span class="muted">[{mark}]</span></div>')
    return "".join(out) or '<span class="muted">No evidence cited</span>'


def _latest(db, cid, agent):
    return (db.query(AgentRun).filter_by(control_id=cid, agent=agent, status="succeeded")
            .order_by(AgentRun.id.desc()).first())


def _run_meta(r):
    if not r:
        return '<p class="muted">Agent has not run.</p>'
    return (f'<p class="muted mono">Agent run #{r.id} · {h(r.model or r.provider)} · prompt {h(r.prompt_version)} · '
            f'input hash {h(r.input_hash[:16])} · {r.created_at:%Y-%m-%d %H:%M} UTC · '
            f'{len(r.guardrail_flags or [])} guardrail flag(s)</p>')


def _conclusion(v, keys):
    if not v:
        return '<div class="banner">Conclusion not yet confirmed by the preparer.</div>'
    rows = "".join(f"<tr><td>{h(k.capitalize())}</td><td><b>{_l(v.get(k))}</b></td></tr>" for k in keys)
    return (f'<table class="kv">{rows}<tr><td>Rationale</td><td>{h(v.get("rationale") or "—")}</td></tr>'
            f'<tr><td>Confirmed by</td><td>{h(v.get("confirmed_by") or "")}'
            f'{" (changed the agent proposal)" if v.get("overrode_agent") else ""}</td></tr></table>')


def render_workpaper(db: Session, c: Control, user: User) -> str:
    users = {u.id: u.name for u in db.query(User)}
    ev = db.query(Evidence).filter_by(control_id=c.id, deleted=False).order_by(Evidence.id).all()
    de, oe = _latest(db, c.id, "design"), _latest(db, c.id, "operating")
    sample = db.query(Sample).filter_by(control_id=c.id, active=True).order_by(Sample.id.desc()).first()
    xs = db.query(Exception_).filter_by(control_id=c.id).order_by(Exception_.id).all()
    notes = db.query(ReviewNote).filter_by(control_id=c.id).order_by(ReviewNote.id).all()
    signs = db.query(SignOff).filter_by(control_id=c.id).order_by(SignOff.id).all()
    attr = {a["id"]: a["text"] for a in c.attributes}
    e = c.engagement
    P = []
    P.append(f'<p class="muted">{h(e.client)} · {h(e.name)} · Period {e.period_start} to {e.period_end}</p>'
             f'<h1><span class="mono">{h(c.ref)}</span> {h(c.title)}</h1>'
             f'<p class="muted">Work paper generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by {h(user.name)} · '
             f'Status: <b>{h(c.status.replace("_", " "))}</b></p>')
    if c.status != "operating_reviewed":
        P.append('<div class="banner">DRAFT: this control has not completed review.</div>')

    P.append('<h2>1. Control</h2><table class="kv">' + "".join(
        f"<tr><td>{k}</td><td>{h(str(v))}</td></tr>" for k, v in [
            ("Description", c.description), ("Objective", c.objective), ("Risk", c.risk),
            ("System", f"{c.system.name} ({c.system.layer})" if c.system else "—"),
            ("Frequency / nature", f"{c.frequency} / {c.nature}"), ("Risk rating", c.risk_rating),
            ("Preparer / reviewer", f"{users.get(c.preparer_id, '—')} / {users.get(c.reviewer_id, '—')}")]) + "</table>")
    P.append("<table><tr><th>Attribute</th><th>What must be true</th></tr>" + "".join(
        f'<tr><td class="mono">{h(k)}</td><td>{h(v)}</td></tr>' for k, v in attr.items()) + "</table>")

    P.append("<h2>2. Evidence</h2><table><tr><th>ID</th><th>File</th><th>Purpose</th><th>SHA-256</th><th>Uploaded</th><th>Intake check</th></tr>")
    for x in ev:
        ik = x.intake or {}
        issues = "; ".join(ik.get("quality_issues", [])) or "No issues noted"
        P.append(f'<tr><td class="mono">E{x.id}</td><td>{h(x.filename)}</td><td>{h(x.purpose)}</td>'
                 f'<td class="mono">{x.sha256[:16]}…</td><td>{x.uploaded_at:%Y-%m-%d} {h(users.get(x.uploaded_by, ""))}</td>'
                 f'<td>{h(ik.get("summary", "—"))}<div class="muted">{h(issues)}</div></td></tr>')
    P.append("</table>" if ev else "</table><p class='muted'>No evidence attached.</p>")

    P.append("<h2>3. Design effectiveness</h2>" + _run_meta(de))
    if de:
        res = (de.result or {}).get("evaluation", {})
        P.append(f"<p>{h(res.get('summary', ''))}</p><table><tr><th>Attribute</th><th>Design</th><th>Implemented</th><th>Reasoning and evidence</th></tr>")
        for a in res.get("attribute_results", []):
            P.append(f'<tr><td><span class="mono">{h(a["attribute_id"])}</span> {h(attr.get(a["attribute_id"], ""))}</td>'
                     f'<td>{_l(a.get("design_assessment"))}</td><td>{_l(a.get("implemented"))}</td>'
                     f'<td>{h(a.get("reasoning", ""))}{_cites(a.get("citations"))}</td></tr>')
        P.append("</table>")
        if res.get("gaps"):
            P.append("<p><b>Gaps:</b> " + h("; ".join(res["gaps"])) + "</p>")
    P.append("<h3>Conclusion (preparer)</h3>" + _conclusion(c.design_conclusion, ("design", "implementation")))

    P.append("<h2>4. Sample</h2>")
    if sample:
        P.append(f'<table class="kv"><tr><td>Method</td><td>{h(sample.method)}</td></tr>'
                 f"<tr><td>Population / sample</td><td>{sample.population_size} / {sample.sample_size}</td></tr>"
                 f'<tr><td>Seed</td><td class="mono">{sample.seed}</td></tr>'
                 f"<tr><td>Basis</td><td>{h(sample.rationale)}</td></tr>"
                 f'<tr><td>Population file</td><td class="mono">{"E" + str(sample.population_evidence_id) if sample.population_evidence_id else "—"}</td></tr></table>')
    else:
        P.append('<p class="muted">No sample selected.</p>')

    P.append("<h2>5. Operating effectiveness</h2>" + _run_meta(oe))
    if oe:
        items = ((oe.result or {}).get("results") or {}).get("items", [])
        P.append("<table><tr><th>#</th><th>Sample item</th>" + "".join(f"<th>{h(k)}</th>" for k in attr) + "</tr>")
        for it in items:
            by = {r["attribute_id"]: r for r in it.get("results", [])}
            cells = "".join(
                f'<td class="cell {by[k]["result"]}">{ {"pass": "✓", "fail": "✗"}.get(by[k]["result"], "?") }</td>'
                if k in by else '<td class="cell">—</td>' for k in attr)
            P.append(f'<tr><td class="mono">{it["sample_index"]}</td><td>{h(it.get("label", ""))}</td>{cells}</tr>')
        P.append("</table><h3>Detail by item</h3>")
        for it in items:
            P.append(f'<div class="box"><b>#{it["sample_index"]} {h(it.get("label", ""))}</b>')
            for r in it.get("results", []):
                P.append(f'<div><span class="mono">{h(r["attribute_id"])}</span> <b>{_l(r["result"])}</b>: '
                         f'{h(r.get("note", ""))}{_cites(r.get("citations"))}</div>')
            P.append("</div>")
    if xs:
        P.append("<h3>Exceptions</h3><table><tr><th>Item</th><th>Attr.</th><th>Description</th><th>Severity</th><th>Status</th></tr>" + "".join(
            f'<tr><td>{h(x.sample_item)}</td><td class="mono">{h(x.attribute_id)}</td><td>{h(x.description)}</td>'
            f"<td>{h(x.severity)}</td><td>{h(x.status)}</td></tr>" for x in xs) + "</table>")
    P.append("<h3>Conclusion (preparer)</h3>" + _conclusion(c.operating_conclusion, ("operating",)))

    P.append("<h2>6. Review notes</h2>")
    P.append(("<table><tr><th>Stage</th><th>Severity</th><th>Note</th><th>Response</th><th>Status</th></tr>" + "".join(
        f"<tr><td>{h(n.stage)}</td><td>{h(n.severity)}</td><td>{h(n.text)}</td><td>{h(n.response)}</td><td>{h(n.status)}</td></tr>"
        for n in notes) + "</table>") if notes else '<p class="muted">None.</p>')

    P.append("<h2>7. Sign-offs</h2>")
    P.append(("<table><tr><th>Stage</th><th>Role</th><th>Name</th><th>Date (UTC)</th><th>Comment</th><th>State</th></tr>" + "".join(
        f"<tr><td>{h(s.stage)}</td><td>{h(s.kind)}</td><td>{h(s.user.name)}</td><td>{s.at:%Y-%m-%d %H:%M}</td>"
        f'<td>{h(s.comment)}</td><td>{"revoked" if s.revoked else "valid"}</td></tr>' for s in signs) + "</table>")
        if signs else '<p class="muted">None.</p>')
    P.append('<p class="muted" style="margin-top:30px">AI agents drafted parts of this work paper. Conclusions and sign-offs '
             "were made by the named people. ✓ means the quoted text was found word for word in the evidence file.</p>")
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{h(c.ref)} work paper</title><style>{CSS}</style></head><body>{"".join(P)}</body></html>'
