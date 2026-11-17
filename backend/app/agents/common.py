import hashlib
import json
import re

from ..config import get_settings
from ..models import Control, Evidence

settings = get_settings()

STOP = {"which", "their", "there", "where", "should", "within", "before", "after", "exists",
        "documented", "appropriate", "control", "system", "access", "users", "each"}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def control_block(c: Control) -> str:
    sysname = f"{c.system.name} ({c.system.layer})" if c.system else "Not specified"
    attrs = "\n".join(f"  {a['id']}: {a['text']}" for a in c.attributes)
    return f"""CONTROL {c.ref} - {c.title}
Domain: {c.domain}   Frequency: {c.frequency}   Nature: {c.nature}   Risk rating: {c.risk_rating}
System in scope: {sysname}
Period: {c.engagement.period_start} to {c.engagement.period_end}
Description: {c.description}
Objective: {c.objective}
Risk: {c.risk}
Attributes:
{attrs}"""


def evidence_block(evidence: list[Evidence]) -> str:
    if not evidence:
        return "EVIDENCE: none provided."
    budget = max(2000, settings.max_evidence_chars // max(1, len(evidence)))
    parts = []
    for e in evidence:
        body = e.extracted_text or f"(no readable text: {e.extraction_note})"
        cut = " [truncated]" if len(body) > budget else ""
        parts.append(f'<evidence id="E{e.id}" file="{e.filename}" purpose="{e.purpose}">\n'
                     f"{body[:budget]}{cut}\n</evidence>")
    return "EVIDENCE DOCUMENTS:\n" + "\n".join(parts)


def input_hash(*objs) -> str:
    return hashlib.sha256(json.dumps(objs, sort_keys=True, default=str).encode()).hexdigest()


def parse_eid(v) -> int | None:
    m = re.match(r"E?(\d+)$", str(v).strip(), re.I)
    return int(m.group(1)) if m else None


def validate_citations(citations: list[dict], evidence: list[Evidence], where: str) -> tuple[list[dict], list[dict]]:
    """Check each citation points at real evidence and the excerpt is actually in it.
    Returns (checked_citations, flags)."""
    by_id = {e.id: e for e in evidence}
    out, flags = [], []
    for cit in citations or []:
        eid = parse_eid(cit.get("evidence_id", ""))
        ev = by_id.get(eid)
        c = dict(cit, evidence_id=f"E{eid}" if eid else str(cit.get("evidence_id")))
        if not ev:
            c["verified"] = False
            flags.append({"type": "unknown_evidence", "where": where,
                          "detail": f"Cited {cit.get('evidence_id')} which is not attached to this control"})
        elif not ev.extracted_text:
            c["verified"] = None  # cannot check (image / unreadable)
            c["filename"] = ev.filename
        else:
            excerpt = norm(cit.get("excerpt", ""))[:120]
            ok = bool(excerpt) and excerpt in norm(ev.extracted_text)
            c["verified"] = ok
            c["filename"] = ev.filename
            if not ok:
                flags.append({"type": "excerpt_not_found", "where": where,
                              "detail": f"Excerpt not found word-for-word in {c['evidence_id']} ({ev.filename})"})
        out.append(c)
    return out, flags


# ------------------------------------------------------------- mock helpers
def keywords(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z]{6,}", text.lower())
    return [w for w in words if w not in STOP][:6]


def find_line(evidence: list[Evidence], terms: list[str], prefer=None):
    """Return (evidence, line) for the first line containing any term."""
    for e in evidence:
        if prefer and e.purpose not in prefer:
            continue
        for line in (e.extracted_text or "").splitlines():
            l = line.lower()
            if line.strip() and any(t in l for t in terms):
                return e, line.strip()[:200]
    if prefer:
        return find_line(evidence, terms)
    return None, None


CITATION_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "evidence_id": {"type": "string", "description": "e.g. E12"},
            "locator": {"type": "string", "description": "page, sheet, row or section"},
            "excerpt": {"type": "string", "description": "short word-for-word quote from the evidence"},
        },
        "required": ["evidence_id", "excerpt"],
    },
}
