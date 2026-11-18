"""Journal entry testing API."""
import csv
import hashlib
import io
import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import audit, journals as J
from ..agents import prompts
from ..agents.llm import call_structured
from ..config import get_settings
from ..db import SessionLocal, get_db
from ..models import JournalBatch, JournalEntry, User
from ..security import ROLE_RANK, current_user
from .engagements import get_engagement

router = APIRouter(tags=["journals"])
settings = get_settings()
log = logging.getLogger("controllens.journals")
EXPLAIN_TOP = 30


def S_batch(b: JournalBatch):
    return {"id": b.id, "filename": b.filename, "sha256": b.sha256, "stats": b.stats, "mapping": b.mapping,
            "explain_status": b.explain_status, "uploaded_at": b.uploaded_at.isoformat(), "uploaded_by": b.uploaded_by}


def S_entry(e: JournalEntry, full=False):
    d = {"id": e.id, "ref": e.ref, "date": e.date.isoformat() if e.date else None,
         "posted_at": e.posted_at.isoformat(sep=" ", timespec="minutes") if e.posted_at else None,
         "user": e.user, "approver": e.approver, "source": e.source, "description": e.description,
         "amount": e.amount, "line_count": e.line_count, "score": e.score, "band": e.band,
         "rules": [h["rule"] for h in e.hits], "disposition": e.disposition, "explained": bool(e.explanation)}
    if full:
        d.update(lines=e.lines, hits=e.hits, explanation=e.explanation, disposition_note=e.disposition_note)
    return d


def _batch(db, bid, user, write=False) -> JournalBatch:
    b = db.get(JournalBatch, bid)
    if not b:
        raise HTTPException(404, "Ledger file not found")
    get_engagement(db, b.engagement_id, user, write)
    return b


def _ingest(db: Session, eid: int, user: User, raw: bytes, filename: str) -> JournalBatch:
    try:
        header, rows = J.read_rows(raw, filename)
        mapping = J.map_columns(header)
        journals, info = J.build_journals(header, rows, mapping)
        if not journals:
            raise J.LedgerError("No journals found. Check the journal ID column has values.")
        stats = J.score_journals(journals, info)
    except J.LedgerError as e:
        raise HTTPException(422, str(e))
    sha = hashlib.sha256(raw).hexdigest()
    folder = Path(settings.storage_dir) / str(eid) / "ledgers"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sha[:16]}_{filename}"
    path.write_bytes(raw)
    b = JournalBatch(engagement_id=eid, filename=filename, sha256=sha, storage_path=str(path), stats=stats,
                     mapping={f: header[i] for f, i in mapping.items()}, uploaded_by=user.id)
    db.add(b)
    db.flush()
    db.bulk_insert_mappings(JournalEntry, [dict(
        batch_id=b.id, ref=j["ref"][:80], date=j["date"], posted_at=j["posted_at"], user=j["user"][:120],
        approver=j["approver"][:120], source=j["source"][:120], description=j["description"], amount=j["debit"],
        line_count=len(j["lines"]), lines=j["lines"][:200], score=j["score"], band=j["band"], hits=j["hits"],
        disposition="open", disposition_note="") for j in journals])
    audit.log(db, user, "journals.uploaded", "journal_batch", b.id,
              {"file": filename, "sha256": sha, "journals": stats["journals"], "lines": stats["lines"],
               "high": stats["bands"]["high"]}, engagement_id=eid)
    db.commit()
    return b


@router.get("/engagements/{eid}/journals")
def list_batches(eid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_engagement(db, eid, user)
    return [S_batch(b) for b in db.query(JournalBatch).filter_by(engagement_id=eid).order_by(JournalBatch.id.desc())]


@router.post("/engagements/{eid}/journals", status_code=201)
async def upload_ledger(eid: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                        user: User = Depends(current_user)):
    get_engagement(db, eid, user, write=True)
    name = Path(file.filename or "ledger.csv").name
    if not name.lower().endswith((".csv", ".txt", ".xlsx", ".xlsm")):
        raise HTTPException(415, "Upload the ledger as CSV or Excel")
    raw = await file.read(60 * 1024 * 1024 + 1)
    if len(raw) > 60 * 1024 * 1024:
        raise HTTPException(413, "File is larger than 60 MB. Split it by period.")
    return S_batch(_ingest(db, eid, user, raw, name))


@router.post("/engagements/{eid}/journals/sample", status_code=201)
def load_sample(eid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    e = get_engagement(db, eid, user, write=True)
    return S_batch(_ingest(db, eid, user, J.sample_ledger(e.period_start.year), "sample_general_ledger.csv"))


@router.delete("/journal-batches/{bid}")
def delete_batch(bid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    b = _batch(db, bid, user, write=True)
    if ROLE_RANK[user.role] < ROLE_RANK["manager"]:
        raise HTTPException(403, "Only managers can remove a ledger file")
    audit.log(db, user, "journals.removed", "journal_batch", b.id, {"file": b.filename, "sha256": b.sha256},
              engagement_id=b.engagement_id)
    db.delete(b)
    db.commit()
    return {"ok": True}


@router.get("/journal-batches/{bid}/entries")
def entries(bid: int, band: str = "", rule: str = "", disposition: str = "", q: str = "", limit: int = 100,
            offset: int = 0, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _batch(db, bid, user)
    qy = db.query(JournalEntry).filter_by(batch_id=bid)
    if band:
        qy = qy.filter_by(band=band)
    if disposition:
        qy = qy.filter_by(disposition=disposition)
    if q:
        like = f"%{q}%"
        qy = qy.filter(or_(JournalEntry.ref.ilike(like), JournalEntry.description.ilike(like), JournalEntry.user.ilike(like)))
    rows = qy.order_by(JournalEntry.score.desc(), JournalEntry.amount.desc()).all() if rule else None
    if rule:  # rule hits live in JSON; filter in code
        rows = [e for e in rows if any(h["rule"] == rule for h in e.hits)]
        total, page = len(rows), rows[offset:offset + min(limit, 500)]
    else:
        total = qy.count()
        page = qy.order_by(JournalEntry.score.desc(), JournalEntry.amount.desc()).offset(offset).limit(min(limit, 500)).all()
    return {"total": total, "items": [S_entry(e) for e in page]}


@router.get("/journal-entries/{jid}")
def entry(jid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    e = db.get(JournalEntry, jid)
    if not e:
        raise HTTPException(404, "Journal not found")
    _batch(db, e.batch_id, user)
    return S_entry(e, full=True)


class Disposition(BaseModel):
    disposition: str
    note: str = ""


@router.patch("/journal-entries/{jid}")
def set_disposition(jid: int, body: Disposition, db: Session = Depends(get_db), user: User = Depends(current_user)):
    e = db.get(JournalEntry, jid)
    if not e:
        raise HTTPException(404, "Journal not found")
    b = _batch(db, e.batch_id, user, write=True)
    if body.disposition not in ("open", "selected", "cleared", "exception"):
        raise HTTPException(422, "disposition must be open, selected, cleared or exception")
    if body.disposition in ("cleared", "exception") and len(body.note.strip()) < 10:
        raise HTTPException(422, "Write a short note on what you checked and found (10+ characters)")
    e.disposition, e.disposition_note, e.disposition_by = body.disposition, body.note.strip(), user.id
    audit.log(db, user, "journals.disposition", "journal_entry", e.id,
              {"ref": e.ref, "disposition": e.disposition, "note": e.disposition_note[:200], "score": e.score},
              engagement_id=b.engagement_id)
    db.commit()
    return S_entry(e, full=True)


# ---------------------------------------------------------------- explain
SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {
    "type": "object", "properties": {"id": {"type": "integer"}, "why_unusual": {"type": "string"},
                                     "what_to_check": {"type": "array", "items": {"type": "string"}}},
    "required": ["id", "why_unusual", "what_to_check"]}}}, "required": ["items"]}
CHECKS = {
    "R01": "Ask why it was posted on a weekend and who was working", "R02": "Ask why it was posted outside working hours",
    "R03": "Obtain the calculation behind the round amount", "R04": "Check whether it was split or sized to avoid a higher approval",
    "R05": "Obtain support and confirm it belongs in this period", "R06": "Obtain the support and approval for the manual entry",
    "R07": "Ask the preparer for the business reason and support", "R08": "Read the support for the adjustment and who asked for it",
    "R09": "Confirm who reviewed it; assess the lack of independent approval", "R10": "Confirm the user's role and why they posted this",
    "R11": "Confirm the account combination makes business sense", "R12": "Agree the amount to source documents",
    "R13": "Compare with the matching journal and confirm it is not booked twice", "R14": "Find the missing lines; confirm the ledger extract is complete",
    "R15": "Ask why it was recorded late and whether the period is right",
}


def _mock_explain(batch):
    out = []
    for e in batch:
        top = sorted(e.hits, key=lambda h: -h["weight"])
        why = (f"[offline mock] Journal {e.ref} for {e.amount:,.2f} scored {e.score}. " +
               " ".join(h["reason"] + "." for h in top[:3]))
        out.append({"id": e.id, "why_unusual": why, "what_to_check": [CHECKS[h["rule"]] for h in top[:4]]})
    return {"items": out}


def explain_batch(bid: int, user_id: int):
    db = SessionLocal()
    try:
        b = db.get(JournalBatch, bid)
        todo = (db.query(JournalEntry).filter(JournalEntry.batch_id == bid, JournalEntry.explanation.is_(None),
                                              JournalEntry.score >= 20)
                .order_by(JournalEntry.score.desc(), JournalEntry.amount.desc()).limit(EXPLAIN_TOP).all())
        try:
            model = ""
            for i in range(0, len(todo), 10):
                chunk = todo[i:i + 10]
                text = "\n\n".join(
                    f"JOURNAL id={e.id} ref={e.ref} date={e.date} posted={e.posted_at} amount={e.amount:,.2f} "
                    f"user={e.user or '-'} approver={e.approver or '-'} source={e.source or '-'}\n"
                    f"description: {e.description or '(none)'}\nlines: " +
                    "; ".join(f"{l['account']} {l['account_name']} Dr {l['debit']:,.2f} Cr {l['credit']:,.2f}" for l in e.lines[:8]) +
                    "\nrules triggered: " + "; ".join(f"{h['name']} ({h['reason']})" for h in e.hits) for e in chunk)
                r = call_structured(tool_name="record_journal_explanations", tool_description="Explain each journal",
                                    schema=SCHEMA, system=prompts.JOURNAL, user=text, role="evaluate",
                                    mock=lambda c=chunk: _mock_explain(c))
                model = r.model
                by_id = {x["id"]: x for x in r.data["items"]}
                for e in chunk:
                    if e.id in by_id:
                        e.explanation = {"why_unusual": by_id[e.id]["why_unusual"], "what_to_check": by_id[e.id]["what_to_check"],
                                         "model": r.model, "prompt_version": prompts.JOURNAL_VERSION}
                db.commit()
            b.explain_status = "done"
            audit.log(db, db.get(User, user_id), "journals.explained", "journal_batch", bid,
                      {"journals": len(todo), "model": model, "prompt_version": prompts.JOURNAL_VERSION},
                      engagement_id=b.engagement_id)
        except Exception as ex:  # noqa: BLE001
            log.warning("explain failed for batch %s: %s", bid, ex)
            db.rollback()
            b = db.get(JournalBatch, bid)
            b.explain_status = "failed"
        db.commit()
    finally:
        db.close()


@router.post("/journal-batches/{bid}/explain", status_code=202)
def explain(bid: int, bg: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(current_user)):
    b = _batch(db, bid, user, write=True)
    if b.explain_status == "running":
        raise HTTPException(409, "Explanations are already being written")
    b.explain_status = "running"
    db.commit()
    bg.add_task(explain_batch, bid, user.id)
    return S_batch(b)


@router.get("/journal-batches/{bid}/export.csv")
def export(bid: int, only: str = "", db: Session = Depends(get_db), user: User = Depends(current_user)):
    b = _batch(db, bid, user)
    q = db.query(JournalEntry).filter_by(batch_id=bid)
    if only == "selected":
        q = q.filter(JournalEntry.disposition != "open")
    else:
        q = q.filter(JournalEntry.score >= 20)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Journal", "Date", "Posted", "Amount", "User", "Approver", "Source", "Description", "Score", "Risk",
                "Rules triggered", "Why unusual", "Decision", "Auditor note"])
    for e in q.order_by(JournalEntry.score.desc()):
        w.writerow([e.ref, e.date or "", e.posted_at or "", f"{e.amount:.2f}", e.user, e.approver, e.source, e.description,
                    e.score, e.band, "; ".join(f"{h['name']}: {h['reason']}" for h in e.hits),
                    (e.explanation or {}).get("why_unusual", ""), e.disposition, e.disposition_note])
    audit.log(db, user, "journals.exported", "journal_batch", bid, {"only": only or "medium and high"}, engagement_id=b.engagement_id)
    db.commit()
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="journal_testing_{bid}.csv"'})
