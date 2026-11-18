"""Evidence intake check. Runs once per file, right after upload, so the team knows
early whether the file is usable and which attributes it supports."""
import csv
import io
import logging
import re

from .. import audit
from ..db import SessionLocal
from ..models import Evidence, Control, User
from . import prompts
from .common import control_block, evidence_attachments, is_visual, keywords
from .llm import call_structured

log = logging.getLogger("controllens.intake")

SCHEMA = {
    "type": "object",
    "properties": {
        "doc_type": {"type": "string", "description": "e.g. policy, walkthrough note, ticket export, screenshot, user listing"},
        "summary": {"type": "string"},
        "period_covered": {"type": "string", "description": "dates the file covers, or 'not stated'"},
        "system_identified": {"type": "string", "description": "system named in the file, or 'not stated'"},
        "supports_attributes": {"type": "array", "items": {"type": "string"}},
        "quality_issues": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["doc_type", "summary", "period_covered", "system_identified",
                 "supports_attributes", "quality_issues"],
}
DATE = re.compile(r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[ -/](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[ -/]20\d{2}|\d{1,2}/\d{1,2}/20\d{2})\b", re.I)


def _population_profile(e: Evidence) -> dict:
    rows = list(csv.reader(io.StringIO(e.extracted_text))) if e.filename.lower().endswith(".csv") else []
    cols = rows[0] if rows else []
    n = max(0, len(rows) - 1)
    issues = [] if n else ["Could not count rows; check the file has a header row and data"]
    return {"doc_type": "population listing", "summary": f"Population file with {n} rows and columns: {', '.join(cols[:12])}." if n
            else "Population file.", "period_covered": "see date columns", "system_identified": "not stated",
            "supports_attributes": [], "quality_issues": issues + ["Document how this listing was produced "
            "(report name, filters, run date) to support completeness"], "rows": n, "columns": cols}


def _mock(e: Evidence, c: Control) -> dict:
    text = e.extracted_text or ""
    if is_visual(e):
        return {"doc_type": "image / scan", "summary": "[offline mock] Stored. Add an API key so the AI can read images and scans.",
                "period_covered": "not stated", "system_identified": "not stated", "supports_attributes": [],
                "quality_issues": ["Not read in offline demo mode"]}
    low = text.lower()
    supports = [a["id"] for a in c.attributes if any(k in low for k in keywords(a["text"]))]
    dates = DATE.findall(text)
    sysname = c.system.name if c.system else ""
    found_sys = bool(sysname) and sysname.split()[0].lower() in low
    issues = []
    if not dates:
        issues.append("No date found in the file")
    if sysname and not found_sys:
        issues.append(f"System name '{sysname}' not found in the file")
    return {"doc_type": "text document", "summary": "[offline mock] " + " ".join(text.split())[:160],
            "period_covered": f"{min(dates)} to {max(dates)}" if dates else "not stated",
            "system_identified": sysname if found_sys else "not stated",
            "supports_attributes": supports, "quality_issues": issues}


def analyze(evidence_id: int):
    """Background task. Uses its own DB session."""
    db = SessionLocal()
    try:
        e = db.get(Evidence, evidence_id)
        if not e or e.deleted:
            return
        c = db.get(Control, e.control_id)
        try:
            if e.purpose == "population":
                data, model = _population_profile(e), "code"
            else:
                body = ("(attached above as an image / scan)" if is_visual(e)
                        else (e.extracted_text[:20000] or f"(no readable text: {e.extraction_note})"))
                r = call_structured(
                    tool_name="record_evidence_intake", tool_description="Record the intake check for one evidence file",
                    schema=SCHEMA, system=prompts.INTAKE, role="plan",
                    user=f"{control_block(c)}\n\nFILE E{e.id}: {e.filename} (uploaded as: {e.purpose})\n{body}",
                    attachments=evidence_attachments([e]), mock=lambda: _mock(e, c))
                data, model = r.data, r.model
                valid = {a["id"] for a in c.attributes}
                data["supports_attributes"] = [a for a in data.get("supports_attributes", []) if a in valid]
            e.intake = dict(data, model=model, prompt_version=prompts.INTAKE_VERSION)
            e.intake_status = "done"
        except Exception as ex:  # noqa: BLE001 - intake must never break the upload
            log.warning("intake failed for evidence %s: %s", evidence_id, ex)
            e.intake_status, e.intake = "failed", {"error": str(ex)[:300]}
        audit.log(db, db.get(User, e.uploaded_by), f"evidence.intake_{e.intake_status}", "evidence", e.id,
                  {"issues": len((e.intake or {}).get("quality_issues", []))},
                  engagement_id=c.engagement_id, control_id=c.id)
        db.commit()
    finally:
        db.close()
