from fastapi.testclient import TestClient

from atlas.api import app

client = TestClient(app)


def test_sante():
    assert client.get("/health").json()["status"] == "ok"


def test_liste_des_modules():
    ids = {m["id"] for m in client.get("/modules").json()}
    assert {"overview", "exposure", "risk"} <= ids


def test_demo_vue_d_ensemble():
    r = client.get("/demo/overview")
    assert r.status_code == 200
    assert any(b["id"] == "value" for b in r.json()["blocks"])


def test_import_puis_calcul():
    csv = "date,type,symbol,quantity,price\n2024-01-02,buy,CW8,5,400\n2024-01-03,buy,???,,\n"
    imp = client.post("/imports", files={"file": ("pf.csv", csv, "text/csv")}).json()
    assert len(imp["transactions"]) == 1 and len(imp["rejected"]) == 1
    r = client.post("/compute/overview", json={"transactions": imp["transactions"], "instruments": imp["instruments"]})
    assert r.status_code == 200


def test_module_inconnu():
    assert client.get("/demo/inexistant").status_code == 404


def test_parametre_invalide():
    pf = client.post("/imports", files={"file": ("pf.csv", "date,type,symbol,quantity,price\n2021-02-01,buy,CW8,5,400\n")}).json()
    r = client.post("/compute/risk", json={"transactions": pf["transactions"], "params": {"lookback_years": 99}})
    assert r.status_code == 422


def test_diagnostic_des_cours():
    from fastapi.testclient import TestClient

    from atlas.api import app
    r = TestClient(app).get("/market/check")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "demo" and set(body["lines"]) >= {"US0378331005", "XF000BTC0017"}
