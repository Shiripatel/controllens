"""First-start data: an admin user, and (optionally) a demo engagement with sample
evidence so the agents can be tried straight away."""
import hashlib
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from . import audit
from .config import get_settings
from .extraction import extract
from .library import LIBRARY
from .models import User, Engagement, EngagementMember, System, Control, Evidence
from .security import hash_password

settings = get_settings()

DEMO_USERS = [
    ("maya.manager@controllens.local", "Maya Manager", "manager"),
    ("priya.preparer@controllens.local", "Priya Preparer", "preparer"),
    ("ravi.reviewer@controllens.local", "Ravi Reviewer", "reviewer"),
]
DEMO_PASSWORD = settings.seed_demo_password

POLICY = """ACME CORP - ACCESS MANAGEMENT POLICY (v3.2, effective 1 Jan 2026)
Section 4.1 New access: All new user access and changes to access must be requested through a ServiceNow access request ticket.
Section 4.2 Approval: The request must be approved by the user's line manager and the system owner before access is granted.
Section 4.3 Set-up: IT Security grants access exactly as approved. The person granting access cannot be the approver.
Section 4.4 Records: Tickets are retained for 7 years.
"""

WALKTHROUGH = """Walkthrough - APD-01 SAP user provisioning - performed 15 Mar 2026 with J. Lee (IT Security)
Ticket RITM0010231 for user ASMITH (new hire, AP clerk) was raised on 02 Mar 2026.
Line manager approval by K. Brown on 02 Mar 2026; system owner approval by P. Diaz on 03 Mar 2026.
Access granted in SAP by J. Lee on 03 Mar 2026: role Z_AP_CLERK, which matches the approved request.
Approver (P. Diaz) is independent of the person granting access (J. Lee).
"""

POPULATION = """user_id,created_on,role,ticket
ASMITH,2026-03-03,Z_AP_CLERK,RITM0010231
BJONES,2026-03-20,Z_GL_ACCT,RITM0010388
CWU,2026-04-11,Z_AR_CLERK,RITM0010502
DPATEL,2026-05-02,Z_AP_CLERK,RITM0010644
EGARCIA,2026-05-28,Z_PURCH,RITM0010790
FKIM,2026-06-15,Z_GL_ACCT,RITM0010901
GLOPEZ,2026-07-07,Z_AP_CLERK,RITM0011012
HNGUYEN,2026-08-19,Z_AR_CLERK,RITM0011230
"""

TICKETS = """ticket,user_id,requested,manager_approval,owner_approval,granted,granted_by,approved_role,granted_role,comment
RITM0010231,ASMITH,2026-03-02,2026-03-02,2026-03-03,2026-03-03,JLEE,Z_AP_CLERK,Z_AP_CLERK,approved
RITM0010388,BJONES,2026-03-18,2026-03-19,2026-03-19,2026-03-20,JLEE,Z_GL_ACCT,Z_GL_ACCT,approved
RITM0010502,CWU,2026-04-09,2026-04-10,2026-04-10,2026-04-11,MCHEN,Z_AR_CLERK,Z_AR_CLERK,approved
RITM0010644,DPATEL,2026-05-01,2026-05-01,2026-05-02,2026-05-02,JLEE,Z_AP_CLERK,Z_AP_CLERK,approved
RITM0010790,EGARCIA,2026-05-26,2026-05-27,2026-05-30,2026-05-28,MCHEN,Z_PURCH,Z_PURCH,owner approval late - access granted before owner approval
RITM0010901,FKIM,2026-06-12,2026-06-13,2026-06-14,2026-06-15,JLEE,Z_GL_ACCT,Z_GL_ACCT,approved
RITM0011012,GLOPEZ,2026-07-03,2026-07-06,2026-07-06,2026-07-07,MCHEN,Z_AP_CLERK,Z_AP_CLERK,approved
RITM0011230,HNGUYEN,2026-08-15,2026-08-18,2026-08-18,2026-08-19,JLEE,Z_AR_CLERK,Z_AR_CLERK,approved
"""


def _add_file(db, c: Control, name, content: str, purpose, user):
    raw = content.encode()
    sha = hashlib.sha256(raw).hexdigest()
    folder = Path(settings.storage_dir) / str(c.engagement_id) / str(c.id)
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"{sha[:16]}_{name}"
    p.write_bytes(raw)
    text, note = extract(raw, name)
    db.add(Evidence(control_id=c.id, filename=name, content_type="text/plain", size=len(raw), sha256=sha,
                    storage_path=str(p), purpose=purpose, extracted_text=text, extraction_note=note,
                    uploaded_by=user.id, description="Demo evidence"))


def run(db: Session):
    if db.query(User).count():
        return
    admin = User(email=settings.seed_admin_email.lower(), name="Administrator", role="admin",
                 password_hash=hash_password(settings.seed_admin_password))
    db.add(admin)
    db.flush()
    audit.log(db, None, "system.seeded", "user", admin.id, {"admin": admin.email})
    if not settings.seed_demo:
        db.commit()
        return
    users = []
    for email, name, role in DEMO_USERS:
        u = User(email=email, name=name, role=role, password_hash=hash_password(DEMO_PASSWORD))
        db.add(u)
        users.append(u)
    db.flush()
    mgr, prep, rev = users
    e = Engagement(name="FY2026 SOX ITGC", client="Acme Corp", period_start=date(2026, 1, 1),
                   period_end=date(2026, 12, 31), created_by=mgr.id)
    db.add(e)
    db.flush()
    for u in (mgr, prep, rev):
        db.add(EngagementMember(engagement_id=e.id, user_id=u.id))
    sap = System(engagement_id=e.id, name="SAP S/4HANA", layer="Application", description="General ledger, AP, AR")
    ora = System(engagement_id=e.id, name="Oracle DB 19c", layer="Database", description="SAP database layer")
    db.add_all([sap, ora])
    db.flush()
    first = None
    for t in LIBRARY:
        c = Control(engagement_id=e.id, system_id=sap.id, library_ref=t["ref"], ref=t["ref"] + "-SAP",
                    domain=t["domain"], title=t["title"], description=t["description"],
                    objective=t["objective"], risk=t["risk"], frequency=t["frequency"], nature=t["nature"],
                    attributes=t["attributes"], design_procedures=t["design_procedures"],
                    operating_procedures=t["operating_procedures"], expected_evidence=t["expected_evidence"],
                    preparer_id=prep.id, reviewer_id=rev.id)
        db.add(c)
        db.flush()
        first = first or c
    _add_file(db, first, "Access_Management_Policy_v3.2.txt", POLICY, "design", prep)
    _add_file(db, first, "APD-01_Walkthrough_RITM0010231.txt", WALKTHROUGH, "design", prep)
    _add_file(db, first, "SAP_new_users_FY26.csv", POPULATION, "population", prep)
    _add_file(db, first, "ServiceNow_access_tickets_FY26.csv", TICKETS, "operating", prep)
    audit.log(db, None, "system.demo_seeded", "engagement", e.id, {}, engagement_id=e.id)
    db.commit()
