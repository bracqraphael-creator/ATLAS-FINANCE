"""Alertes : franchissements de seuil, valeurs attendues calculées à la main."""

import pandas as pd
import pytest

from atlas.core.alerts import AlertRule, evaluate, rsi
from atlas.core.market import MarketData
from atlas.core.models import Instrument, Portfolio
from tests.conftest import tx


def md(closes: dict[str, list[float]], start="2024-01-01"):
    idx = pd.bdate_range(start, periods=len(next(iter(closes.values()))))
    return MarketData(closes={s: pd.Series(v, index=idx) for s, v in closes.items()},
                      currencies={s: "EUR" for s in closes}, source="test")


PF = Portfolio(transactions=[tx("2024-01-01", "buy", "SAF", 10, 100), tx("2024-01-01", "buy", "AIR", 5, 50)],
               instruments={"SAF": Instrument(symbol="SAF", name="Safran")})


def rule(kind, threshold, symbol=None, direction="below"):
    return AlertRule(id="r1", kind=kind, symbol=symbol, threshold=threshold, direction=direction)


def test_variation_d_une_seance_sur_toutes_les_lignes():
    # SAF : 100 -> 93 = −7 % ; AIR : 50 -> 49 = −2 % ; seuil 5 % à la baisse -> seule SAF déclenche
    events = evaluate(PF, md({"SAF": [100, 100, 93], "AIR": [50, 50, 49]}), [rule("line_move", 5)])
    assert [(e.symbol, e.value) for e in events] == [("SAF", -7.0)]
    e = events[0]
    assert e.key == "r1:SAF:2024-01-03" and "Safran a varié de −7,00 %" in e.message.replace(" ", " ")
    # À la hausse uniquement : rien
    assert evaluate(PF, md({"SAF": [100, 100, 93], "AIR": [50, 50, 49]}), [rule("line_move", 5, direction="above")]) == []


def test_passage_sous_le_prix_de_revient_une_seule_fois():
    # PRU 100 ; seuil 10 % -> niveau 90. 95 -> 89 : franchi. Puis 89 -> 85 : déjà sous le seuil, pas de répétition.
    r = [rule("below_cost", 10, "SAF")]
    assert [e.value for e in evaluate(PF, md({"SAF": [100, 95, 89]}), r)] == [-11.0]
    assert evaluate(PF, md({"SAF": [100, 89, 85]}), r) == []


def test_franchissement_d_un_cours_dans_les_deux_sens():
    up = evaluate(PF, md({"SAF": [100, 119, 121]}), [rule("price_cross", 120, "SAF", "both")])
    assert len(up) == 1 and "au-dessus de 120" in up[0].message
    down = evaluate(PF, md({"SAF": [100, 121, 119]}), [rule("price_cross", 120, "SAF", "above")])
    assert down == []                                   # sens « au-dessus » seulement


def test_rsi_wilder_et_franchissement():
    # Hausse continue : aucune baisse -> RSI = 100
    assert rsi(pd.Series(range(1, 30), dtype=float)).iloc[-1] == 100
    # Calcul de référence par une boucle explicite (moyennes de Wilder)
    s = pd.Series([44, 44.3, 44.1, 43.6, 44.3, 44.8, 45.1, 45.4, 45.8, 46.1, 45.9, 46.2, 45.6, 46.3, 46.3, 46.0, 46.4], dtype=float)
    d = s.diff().dropna().tolist()
    ag, al = max(d[0], 0), max(-d[0], 0)
    for x in d[1:]:
        ag += (max(x, 0) - ag) / 14
        al += (max(-x, 0) - al) / 14
    assert rsi(s).iloc[-1] == pytest.approx(100 - 100 / (1 + ag / al))
    # Une série qui baisse puis remonte fort : le RSI repasse au-dessus de 70 à la dernière séance
    closes = [100 - i for i in range(15)] + [86 + 4 * i for i in range(1, 12)]
    r = rsi(pd.Series(closes, dtype=float))
    crossing = next(i for i in range(1, len(r)) if r.iloc[i - 1] <= 70 < r.iloc[i])
    events = evaluate(PF, md({"SAF": closes[: crossing + 1]}), [rule("rsi", 70, "SAF", "above")])
    assert len(events) == 1 and events[0].value > 70


def test_baisse_du_portefeuille_depuis_son_plus_haut():
    # Une seule ligne, 10 titres : 100, 110 (plus haut), 100 (−9,1 %), 98 (−10,9 %) -> seuil 10 % franchi le 4e jour
    pf = Portfolio(transactions=[tx("2024-01-01", "buy", "SAF", 10, 100)])
    events = evaluate(pf, md({"SAF": [100, 110, 100, 98]}), [rule("drawdown", 10)])
    assert len(events) == 1 and events[0].value == pytest.approx(-10.91, abs=0.01)
    assert "plus haut du 02/01/2024" in events[0].message
    # Un jour plus tôt, seuil pas encore franchi
    assert evaluate(pf, md({"SAF": [100, 110, 100]}), [rule("drawdown", 10)]) == []


def test_ligne_sans_cours_ou_vendue_ignoree():
    pf = Portfolio(transactions=PF.transactions + [tx("2024-01-02", "sell", "AIR", 5, 50)])
    events = evaluate(pf, md({"SAF": [100, 100, 100], "AIR": [50, 50, 40]}), [rule("line_move", 5)])
    assert events == []                                  # AIR vendue, plus surveillée


def test_endpoint_alertes():
    from fastapi.testclient import TestClient

    from atlas.api import app
    body = {"transactions": [{"date": "2024-01-02", "type": "buy", "symbol": "CW8", "quantity": 1, "price": 400}],
            "rules": [{"id": "a", "kind": "line_move", "threshold": 5}]}
    r = TestClient(app).post("/alerts/evaluate", json=body)
    assert r.status_code == 200 and "events" in r.json()
