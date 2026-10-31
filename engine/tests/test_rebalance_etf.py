"""Rééquilibrage et comparateur d'ETF : valeurs attendues calculées à la main."""

import pandas as pd
import pytest

from atlas.core.market import MarketData
from atlas.core.models import Instrument, Portfolio
from atlas.core.registry import run
from atlas.modules.etf_compare.compute import lookup
from atlas.modules.rebalance.compute import split_contribution
from tests.conftest import tx


def blocks(result):
    return {b.id: b for b in result.blocks}


def md(closes, periods=None, start="2024-01-01"):
    n = periods or len(next(iter(closes.values())))
    idx = pd.bdate_range(start, periods=n)
    return MarketData(closes={s: pd.Series(v, index=idx) for s, v in closes.items()},
                      currencies={s: "EUR" for s in closes}, source="test")


# Portefeuille : A vaut 7 000 €, B 3 000 € (cible 60 / 40)
PF = Portfolio(transactions=[tx("2024-01-01", "buy", "A", 70, 100), tx("2024-01-01", "buy", "B", 30, 100)],
               instruments={"A": Instrument(symbol="A", name="Monde"), "B": Instrument(symbol="B", name="Émergents")})
MD = md({"A": [100, 100], "B": [100, 100]})


def test_ecart_a_la_cible():
    b = blocks(run("rebalance", PF, MD, {"targets": {"A": 60, "B": 40}}))
    a = next(r for r in b["lines"].rows if r["symbol"] == "A")
    # A : 70 % pour 60 % visés -> +10 points ; 6 000 − 7 000 = −1 000 € à combler
    assert (a["current"], a["target"], a["drift_pts"], a["gap_eur"]) == (70.0, 60.0, 10.0, -1000.0)
    assert b["drift"].value == 10.0                    # (10 + 10) / 2


def test_versement_sans_vente():
    # Versement 1 000 € : total 11 000 ; cibles 6 600 / 4 400 ; manques 0 / 1 400 > 1 000 -> tout sur B
    assert split_contribution({"A": 7000, "B": 3000}, {"A": 0.6, "B": 0.4}, 1000) == pytest.approx({"A": 0, "B": 1000})
    # Versement 5 000 € : total 15 000 ; cibles 9 000 / 6 000 ; manques 2 000 / 3 000 = 5 000 -> exactement
    assert split_contribution({"A": 7000, "B": 3000}, {"A": 0.6, "B": 0.4}, 5000) == pytest.approx({"A": 2000, "B": 3000})
    # Versement 7 000 € : manques 2 600 + 3 400 = 6 000 ; surplus 1 000 réparti 60 / 40
    assert split_contribution({"A": 7000, "B": 3000}, {"A": 0.6, "B": 0.4}, 7000) == pytest.approx({"A": 3200, "B": 3800})
    b = blocks(run("rebalance", PF, MD, {"targets": {"A": 60, "B": 40}, "contribution": 5000}))
    assert b["drift_after"].value == pytest.approx(0.0)


def test_cible_absente_et_poids_ramenes_a_100():
    b = blocks(run("rebalance", PF, MD, {}))
    assert "no-target" in b and b["drift"].value == 0.0
    b = blocks(run("rebalance", PF, MD, {"targets": {"A": 3, "B": 2}}))   # 3:2 -> 60 / 40
    assert next(r for r in b["lines"].rows if r["symbol"] == "B")["target"] == 40.0
    assert "normalized" in b


def test_ligne_cible_non_detenue():
    b = blocks(run("rebalance", PF, MD, {"targets": {"A": 50, "B": 30, "C": 20}}))
    c = next(r for r in b["lines"].rows if r["symbol"] == "C")
    assert (c["value"], c["gap_eur"]) == (0.0, 2000.0)


def test_reglage_allocation_invalide():
    with pytest.raises(ValueError):
        run("rebalance", PF, MD, {"targets": {"A": -5}})


def test_reference_etf_par_isin_et_ticker():
    assert lookup("IE00B4L5Y983")["ter"] == 0.20
    assert lookup("CW8.PA")["isin"] == "LU1681043599"
    assert lookup("XX0000000000") is None


def test_comparateur_mesures():
    # 300 séances (un peu plus d'un an) : X double linéairement, Y reste stable
    n = 300
    x = [100 + 100 * i / (n - 1) for i in range(n)]
    pf = Portfolio(transactions=[tx("2023-01-02", "buy", "IE00B4L5Y983", 1, 100)])
    b = blocks(run("etf_compare", pf, md({"IE00B4L5Y983": x, "CSPX": [50.0] * n}, start="2023-01-02"),
                   {"compare": "IE00B4L5Y983, CSPX", "history_years": 5}))
    rows = {r["symbol"]: r for r in b["compare"].rows}
    assert rows["IE00B4L5Y983"]["ter"] == 0.20 and rows["IE00B4L5Y983"]["pea"] == "non"
    assert rows["CSPX"]["perf_1y"] == 0.0 and rows["CSPX"]["max_dd"] == 0.0
    assert rows["IE00B4L5Y983"]["perf_1y"] > 0 and rows["IE00B4L5Y983"]["perf_3y"] is None   # moins de 3 ans
    assert b["fees"].bars[1]["value"] == 7.0          # CSPX : 0,07 % de 10 000 € = 7 €
    assert "growth" in b


def test_comparateur_par_defaut_etf_du_portefeuille_et_vide():
    pf = Portfolio(transactions=[tx("2024-01-01", "buy", "CW8", 1, 100), tx("2024-01-01", "buy", "MC", 1, 600)],
                   instruments={"MC": Instrument(symbol="MC", asset_class="equity")})
    b = blocks(run("etf_compare", pf, md({"CW8": [100, 101], "MC": [600, 601]}), {}))
    assert [r["symbol"] for r in b["compare"].rows] == ["CW8"]
    assert "empty" in blocks(run("etf_compare", Portfolio(), md({"CW8": [1, 1]}), {}))
