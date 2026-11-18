import base64
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.agents import common, llm
from app.main import app
from app.seed import DEMO_PASSWORD

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def H(client):
    def login(email):
        r = client.post("/api/auth/login", json={"email": email, "password": DEMO_PASSWORD})
        return {"Authorization": f"Bearer {r.json()['token']}"}
    return {"prep": login("shirish@controllens.local"), "rev": login("ravi.reviewer@controllens.local")}


def control(client, H, ref):
    eng = client.get("/api/engagements", headers=H["prep"]).json()[0]
    cs = client.get(f"/api/engagements/{eng['id']}/controls", headers=H["prep"]).json()
    return eng, next(c for c in cs if c["ref"].startswith(ref))


def test_intake_runs_after_upload(client, H):
    _, c = control(client, H, "PC-01")
    up = client.post(f"/api/controls/{c['id']}/evidence", headers=H["prep"], data={"purpose": "design"},
                     files={"file": ("change_policy.txt", b"Change policy 2026-01-05. Every change needs a ticket and CAB approval before deployment.", "text/plain")})
    assert up.status_code == 201
    ev = client.get(f"/api/controls/{c['id']}/evidence", headers=H["prep"]).json()[0]
    assert ev["intake_status"] == "done"
    assert "A2" in ev["intake"]["supports_attributes"] or ev["intake"]["supports_attributes"]
    assert any("System name" in i for i in ev["intake"]["quality_issues"])
    pop = client.post(f"/api/controls/{c['id']}/evidence", headers=H["prep"], data={"purpose": "population"},
                      files={"file": ("changes.csv", b"change,deployed\nCHG1,2026-02-01\nCHG2,2026-03-01\n", "text/csv")}).json()
    ev = [e for e in client.get(f"/api/controls/{c['id']}/evidence", headers=H["prep"]).json() if e["id"] == pop["id"]][0]
    assert ev["intake"]["rows"] == 2 and ev["intake"]["model"] == "code"


def test_requests_draft_link_and_export(client, H):
    eng, c = control(client, H, "PC-02")
    drafted = client.post(f"/api/controls/{c['id']}/requests/draft", headers=H["prep"]).json()
    assert len(drafted) == 2 and all(r["source"] == "agent" for r in drafted)
    assert client.post(f"/api/controls/{c['id']}/requests/draft", headers=H["prep"]).json() == []  # no duplicates
    rid = drafted[0]["id"]
    up = client.post(f"/api/controls/{c['id']}/evidence", headers=H["prep"],
                     data={"purpose": "operating", "request_id": str(rid)},
                     files={"file": ("uat.txt", b"UAT sign-off 2026-04-02 approved by K. Brown", "text/plain")})
    assert up.status_code == 201
    r = [x for x in client.get(f"/api/controls/{c['id']}/requests", headers=H["prep"]).json() if x["id"] == rid][0]
    assert r["status"] == "received" and r["evidence_ids"] == [up.json()["id"]]
    assert client.patch(f"/api/requests/{rid}", json={"status": "closed"}, headers=H["prep"]).json()["status"] == "closed"
    assert client.patch(f"/api/requests/{rid}", json={"evidence_ids": [999999]}, headers=H["prep"]).status_code == 422
    allr = client.get(f"/api/engagements/{eng['id']}/requests", headers=H["prep"]).json()
    assert any(x["control_ref"].startswith("PC-02") for x in allr)
    assert "PC-02" in client.get(f"/api/engagements/{eng['id']}/requests.csv", headers=H["prep"]).text


def test_workpaper_export(client, H):
    _, c = control(client, H, "PC-01")
    client.post(f"/api/controls/{c['id']}/runs", json={"agent": "design"}, headers=H["prep"])
    r = client.get(f"/api/controls/{c['id']}/workpaper.html", headers=H["prep"])
    assert r.status_code == 200 and "PC-01" in r.text and "Design effectiveness" in r.text
    assert "change_policy.txt" in r.text and "DRAFT" in r.text


def test_run_limit(client, H, monkeypatch):
    from app.routers import controls as rc
    _, c = control(client, H, "CO-01")
    monkeypatch.setattr(rc.settings, "max_runs_per_hour", 0)
    assert client.post(f"/api/controls/{c['id']}/runs", json={"agent": "design"}, headers=H["prep"]).status_code == 429


def test_visual_evidence_goes_to_model(tmp_path, monkeypatch):
    p = tmp_path / "shot.png"
    p.write_bytes(PNG)
    img = SimpleNamespace(id=7, filename="sap_password_settings.png", purpose="design", extracted_text="",
                          extraction_note="Image stored", storage_path=str(p))
    txt = SimpleNamespace(id=8, filename="policy.txt", purpose="design", extracted_text="Minimum length 12",
                          extraction_note="Text", storage_path="x")
    assert common.is_visual(img) and not common.is_visual(txt)
    assert common.evidence_attachments([img, txt]) == []          # offline mode sends nothing
    monkeypatch.setattr(llm, "provider_name", lambda: "anthropic")
    blocks = common.evidence_attachments([img, txt])
    assert [b["type"] for b in blocks] == ["text", "image"] and "E7" in blocks[0]["text"]
    assert blocks[1]["source"]["media_type"] == "image/png"
    assert "attached above" in common.evidence_block([img, txt])
    cits, flags = common.validate_citations([{"evidence_id": "E7", "excerpt": "Min length 12"}], [img, txt], "A1")
    assert cits[0]["verified"] is None and cits[0]["visual"] and not flags


def test_model_per_step(monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_model_test", "claude-haiku-5-5")
    assert llm.model_for("test") == "claude-haiku-5-5"
    assert llm.model_for("evaluate") == llm.settings.llm_model
