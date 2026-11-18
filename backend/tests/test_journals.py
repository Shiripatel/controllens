import pytest
from fastapi.testclient import TestClient

from app import journals as J
from app.main import app
from app.seed import DEMO_PASSWORD


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def H(client):
    def login(email):
        r = client.post("/api/auth/login", json={"email": email, "password": DEMO_PASSWORD})
        return {"Authorization": f"Bearer {r.json()['token']}"}
    return {"prep": login("shirish@controllens.local"), "mgr": login("maya.manager@controllens.local")}


def test_scoring_engine_finds_planted_entries():
    header, rows = J.read_rows(J.sample_ledger(2026), "gl.csv")
    journals, info = J.build_journals(header, rows, J.map_columns(header))
    stats = J.score_journals(journals, info)
    assert stats["journals"] > 300 and stats["bands"]["high"] >= 4
    top = sorted(journals, key=lambda j: -j["score"])[:6]
    descs = " ".join(j["description"] for j in top)
    assert "Adjust revenue per CFO" in descs and "plug" in descs
    cfo = next(j for j in journals if j["description"] == "Adjust revenue per CFO")
    rules = {h["rule"] for h in cfo["hits"]}
    assert {"R01", "R02", "R03", "R06", "R08", "R09"} <= rules and cfo["band"] == "high"
    dup = [j for j in journals if j["description"] == "Consulting services"]
    assert all(any(h["rule"] == "R13" for h in j["hits"]) and any(h["rule"] == "R04" for h in j["hits"]) for j in dup)
    late = next(j for j in journals if j["description"] == "Late booked invoice")
    assert any(h["rule"] == "R15" for h in late["hits"])
    # most ordinary entries stay low
    assert stats["bands"]["low"] / stats["journals"] > 0.85
    # same file, same result
    j2, i2 = J.build_journals(header, rows, J.map_columns(header))
    assert J.score_journals(j2, i2)["bands"] == stats["bands"]


def test_column_mapping_and_errors():
    m = J.map_columns(["Doc No", "Posting Date", "GL Account", "Amount", "User", "Text"])
    assert set(m) >= {"journal_id", "date", "account", "amount", "user", "description"}
    with pytest.raises(J.LedgerError):
        J.map_columns(["foo", "bar"])
    header, rows = J.read_rows(b"Doc No;Posting Date;GL Account;Amount\nA1;31/12/2026;4000;(1,500.00)\nA1;31/12/2026;1200;1500\n", "x.csv")
    js, info = J.build_journals(header, rows, J.map_columns(header))
    assert js[0]["debit"] == 1500 and js[0]["credit"] == 1500 and js[0]["date"].month == 12


def test_journal_api_flow(client, H):
    eid = client.get("/api/engagements", headers=H["prep"]).json()[0]["id"]
    b = client.post(f"/api/engagements/{eid}/journals/sample", headers=H["prep"])
    assert b.status_code == 201, b.text
    bid = b.json()["id"]
    assert b.json()["stats"]["bands"]["high"] >= 4
    hi = client.get(f"/api/journal-batches/{bid}/entries?band=high", headers=H["prep"]).json()
    assert hi["total"] >= 4 and hi["items"][0]["score"] >= hi["items"][-1]["score"]
    r13 = client.get(f"/api/journal-batches/{bid}/entries?rule=R13", headers=H["prep"]).json()
    assert r13["total"] == 2
    assert client.get(f"/api/journal-batches/{bid}/entries?q=plug", headers=H["prep"]).json()["total"] == 1
    jid = hi["items"][0]["id"]
    assert client.post(f"/api/journal-batches/{bid}/explain", headers=H["prep"]).status_code == 202
    d = client.get(f"/api/journal-entries/{jid}", headers=H["prep"]).json()
    assert d["explanation"]["why_unusual"] and d["explanation"]["what_to_check"] and len(d["lines"]) == 2
    assert client.get(f"/api/engagements/{eid}/journals", headers=H["prep"]).json()[0]["explain_status"] == "done"
    assert client.patch(f"/api/journal-entries/{jid}", json={"disposition": "cleared"}, headers=H["prep"]).status_code == 422
    ok = client.patch(f"/api/journal-entries/{jid}", headers=H["prep"],
                      json={"disposition": "exception", "note": "No support provided for the adjustment."})
    assert ok.status_code == 200 and ok.json()["disposition"] == "exception"
    csvt = client.get(f"/api/journal-batches/{bid}/export.csv?only=selected", headers=H["prep"]).text
    assert "No support provided" in csvt
    bad = client.post(f"/api/engagements/{eid}/journals", headers=H["prep"], files={"file": ("gl.csv", b"a,b\n1,2\n", "text/csv")})
    assert bad.status_code == 422 and "Could not find" in bad.json()["detail"]
    assert client.delete(f"/api/journal-batches/{bid}", headers=H["prep"]).status_code == 403
    assert client.delete(f"/api/journal-batches/{bid}", headers=H["mgr"]).status_code == 200
