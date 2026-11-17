import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seed import DEMO_PASSWORD  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def login(client, email, pw=DEMO_PASSWORD):
    r = client.post("/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def H(client):
    return {"prep": login(client, "priya.preparer@controllens.local"),
            "rev": login(client, "ravi.reviewer@controllens.local"),
            "mgr": login(client, "maya.manager@controllens.local"),
            "admin": login(client, "admin@controllens.local", "Admin#12345")}


def apd01(client, H):
    eng = client.get("/api/engagements", headers=H["prep"]).json()[0]
    cs = client.get(f"/api/engagements/{eng['id']}/controls", headers=H["prep"]).json()
    return next(c for c in cs if c["ref"].startswith("APD-01"))


def test_auth_required(client):
    assert client.get("/api/engagements").status_code == 401


def test_wrong_password_and_lockout(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"email": "ravi.reviewer@controllens.local",
                                                    "password": "nope"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": "ravi.reviewer@controllens.local", "password": DEMO_PASSWORD})
    assert r.status_code == 423
    # unlock for the rest of the tests
    from app.db import SessionLocal
    from app.models import User
    with SessionLocal() as db:
        u = db.query(User).filter_by(email="ravi.reviewer@controllens.local").one()
        u.locked_until = None
        db.commit()


def test_full_itgc_flow(client, H):
    c = apd01(client, H)
    cid = c["id"]
    ev = client.get(f"/api/controls/{cid}/evidence", headers=H["prep"]).json()
    assert len(ev) == 4

    # Design Effectiveness agent
    r = client.post(f"/api/controls/{cid}/runs", json={"agent": "design"}, headers=H["prep"])
    assert r.status_code == 202
    run = client.get(f"/api/runs/{r.json()['id']}", headers=H["prep"]).json()
    assert run["status"] == "succeeded", run["error"]
    assert [s["key"] for s in run["steps"]] == ["context", "plan", "evaluate", "guardrails", "conclude"]
    proposed = run["result"]["proposed_conclusion"]

    # Preparer cannot sign before confirming the conclusion
    r = client.post(f"/api/controls/{cid}/signoffs", json={"stage": "design", "kind": "prepare"}, headers=H["prep"])
    assert r.status_code == 409

    # Override without reason is rejected
    r = client.post(f"/api/controls/{cid}/conclusion", headers=H["prep"], json={
        "stage": "design", "run_id": run["id"], "conclusion": {"design": "not_effective", "implementation": "implemented"}})
    assert r.status_code == 422
    r = client.post(f"/api/controls/{cid}/conclusion", headers=H["prep"], json={
        "stage": "design", "run_id": run["id"],
        "conclusion": {"design": "effective", "implementation": "implemented"},
        "rationale": "Policy and walkthrough support all four attributes."})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/controls/{cid}/signoffs", json={"stage": "design", "kind": "prepare"},
                       headers=H["prep"]).status_code == 201

    # Preparer cannot review own work (SoD) - manager prepared? no: prep did; manager role ok but test prep
    r = client.post(f"/api/controls/{cid}/signoffs", json={"stage": "design", "kind": "review"}, headers=H["prep"])
    assert r.status_code == 403
    # Open review note blocks review
    n = client.post(f"/api/controls/{cid}/notes", json={"stage": "design", "text": "Add walkthrough date"},
                    headers=H["rev"]).json()
    assert client.post(f"/api/controls/{cid}/signoffs", json={"stage": "design", "kind": "review"},
                       headers=H["rev"]).status_code == 409
    assert client.patch(f"/api/notes/{n['id']}", json={"status": "closed"}, headers=H["prep"]).status_code == 403
    assert client.patch(f"/api/notes/{n['id']}", json={"status": "closed"}, headers=H["rev"]).status_code == 200
    r = client.post(f"/api/controls/{cid}/signoffs", json={"stage": "design", "kind": "review"}, headers=H["rev"])
    assert r.status_code == 201 and r.json()["status"] == "design_reviewed"

    # OE without sample fails cleanly
    r = client.post(f"/api/controls/{cid}/runs", json={"agent": "operating"}, headers=H["prep"])
    run = client.get(f"/api/runs/{r.json()['id']}", headers=H["prep"]).json()
    assert run["status"] == "failed" and "sample" in run["error"].lower()

    # Sampling: event-driven, moderate -> 25, population 8 -> test all
    pop = next(e for e in ev if e["purpose"] == "population")
    s = client.post(f"/api/controls/{cid}/sampling", json={"population_evidence_id": pop["id"], "seed": 42},
                    headers=H["prep"]).json()
    assert s["population_size"] == 8 and s["sample_size"] == 8 and s["method"] == "all_items"

    r = client.post(f"/api/controls/{cid}/runs", json={"agent": "operating"}, headers=H["prep"])
    run = client.get(f"/api/runs/{r.json()['id']}", headers=H["prep"]).json()
    assert run["status"] == "succeeded", run["error"]
    assert run["result"]["proposed_conclusion"]["operating"] == "not_operating_effectively"
    xs = client.get(f"/api/controls/{cid}/exceptions", headers=H["prep"]).json()
    assert xs and all("EGARCIA" in x["sample_item"] for x in xs)

    # Reviewer agent raises notes
    r = client.post(f"/api/controls/{cid}/runs", json={"agent": "reviewer"}, headers=H["rev"])
    rr = client.get(f"/api/runs/{r.json()['id']}", headers=H["rev"]).json()
    assert rr["status"] == "succeeded", rr["error"]
    texts = [n["text"] for n in client.get(f"/api/controls/{cid}/notes", headers=H["rev"]).json()]
    assert any("Operating conclusion has not been confirmed" in t for t in texts)

    # Evidence change revokes Design sign-offs
    up = client.post(f"/api/controls/{cid}/evidence", headers=H["prep"],
                     files={"file": ("extra.txt", b"Additional design note", "text/plain")},
                     data={"purpose": "design"})
    assert up.status_code == 201
    ctl = client.get(f"/api/controls/{cid}", headers=H["prep"]).json()
    assert ctl["status"] == "design_in_progress"
    assert all(s["revoked"] for s in ctl["signoffs"])

    # Duplicate upload blocked, bad file type blocked
    assert client.post(f"/api/controls/{cid}/evidence", headers=H["prep"],
                       files={"file": ("extra.txt", b"Additional design note", "text/plain")},
                       data={"purpose": "design"}).status_code == 409
    assert client.post(f"/api/controls/{cid}/evidence", headers=H["prep"],
                       files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 415


def test_optimistic_locking(client, H):
    c = client.get(f"/api/controls/{apd01(client, H)['id']}", headers=H["prep"]).json()
    ok = client.patch(f"/api/controls/{c['id']}", json={"row_version": c["row_version"], "risk_rating": "High"},
                      headers=H["prep"])
    assert ok.status_code == 200
    stale = client.patch(f"/api/controls/{c['id']}", json={"row_version": c["row_version"], "risk_rating": "Low"},
                         headers=H["prep"])
    assert stale.status_code == 409


def test_sample_size_override_rules(client, H):
    eng = client.get("/api/engagements", headers=H["prep"]).json()[0]
    cs = client.get(f"/api/engagements/{eng['id']}/controls", headers=H["prep"]).json()
    c = next(x for x in cs if x["ref"].startswith("APD-02"))
    pop = "user,term_date\n" + "\n".join(f"U{i},2026-0{1 + i % 9}-10" for i in range(60))
    e = client.post(f"/api/controls/{c['id']}/evidence", headers=H["prep"],
                    files={"file": ("terms.csv", pop.encode(), "text/csv")}, data={"purpose": "population"}).json()
    s = client.post(f"/api/controls/{c['id']}/sampling", json={"population_evidence_id": e["id"], "seed": 7},
                    headers=H["prep"]).json()
    assert s["sample_size"] == 25 and s["method"] == "random"
    # same seed -> same selection (repeatable)
    s2 = client.post(f"/api/controls/{c['id']}/sampling", json={"population_evidence_id": e["id"], "seed": 7},
                     headers=H["prep"]).json()
    assert [i["index"] for i in s["items"]] == [i["index"] for i in s2["items"]]
    assert client.post(f"/api/controls/{c['id']}/sampling", headers=H["prep"], json={
        "population_evidence_id": e["id"], "override_size": 10, "override_reason": "reliance on prior year"}).status_code == 403
    assert client.post(f"/api/controls/{c['id']}/sampling", headers=H["rev"], json={
        "population_evidence_id": e["id"], "override_size": 10, "override_reason": "short"}).status_code == 422


def test_roles(client, H):
    assert client.post("/api/engagements", headers=H["prep"], json={
        "name": "x", "client": "y", "period_start": "2026-01-01", "period_end": "2026-12-31"}).status_code == 403
    assert client.post("/api/users", headers=H["mgr"], json={
        "email": "a@b.co", "name": "A", "role": "viewer", "password": "Abcdefgh12"}).status_code == 403
    assert client.post("/api/users", headers=H["admin"], json={
        "email": "a@b.co", "name": "A", "role": "viewer", "password": "weak"}).status_code == 422


def test_audit_chain_and_tamper_detection(client, H):
    v = client.get("/api/audit/verify", headers=H["mgr"]).json()
    assert v["valid"] and v["checked"] > 10
    from app.db import SessionLocal
    from app.models import AuditLog
    with SessionLocal() as db:
        row = db.query(AuditLog).order_by(AuditLog.id).offset(3).first()
        row.details = {"tampered": True}
        db.commit()
    v = client.get("/api/audit/verify", headers=H["mgr"]).json()
    assert not v["valid"] and v["broken_at_id"] is not None
