"""Modules Dividendes et Plus-values : valeurs attendues calculées à la main."""

import pandas as pd
import pytest

from atlas.core.market import MarketData
from atlas.core.models import Instrument, Portfolio
from atlas.core.registry import registry, run
from tests.conftest import tx


def blocks(result):
    return {b.id: b for b in result.blocks}


EMPTY = MarketData(closes={}, currencies={}, fx={}, source="test")


def usd_market():
    """1 USD = 0,90 € en 2023, 0,80 € en 2024 (taux constant chaque année)."""
    idx = pd.bdate_range("2023-01-02", "2024-12-31")
    rate = pd.Series([0.9 if d.year == 2023 else 0.8 for d in idx], index=idx)
    return MarketData(closes={}, currencies={}, fx={"USD": rate}, source="test")


def test_modules_enregistres_et_ranges():
    reg = registry()
    assert reg["dividends"].manifest["family"] == "portefeuille"
    assert reg["capital_gains"].manifest["family"] == "fiscalite"


# --------------------------------------------------------------------------- Dividendes
def test_dividendes_totaux_annees_et_rendement_sur_cout():
    pf = Portfolio(transactions=[
        tx("2022-03-01", "buy", "TTE", 10, 50),                # 500 € investis
        tx("2022-06-01", "dividend", "TTE", amount=7),
        tx("2024-01-15", "dividend", "TTE", amount=8),
        tx("2024-06-15", "dividend", "TTE", amount=9),
        tx("2024-06-20", "buy", "ORA", 50, 10, fees=1),        # 501 € investis (frais inclus)
        tx("2024-07-01", "dividend", "ORA", amount=15),
    ], instruments={"TTE": Instrument(symbol="TTE", name="TotalEnergies")})
    b = blocks(run("dividends", pf, EMPTY, {"as_of": "2024-12-31"}))
    assert b["total"].value == 39                       # 7 + 8 + 9 + 15
    assert b["last_12m"].value == 32                    # versements après le 01/01/2024 : 8 + 9 + 15
    assert b["this_year"].value == 32
    # 32 / (500 + 501) = 3,1968… %
    assert b["yield_on_cost"].value == pytest.approx(3.2, abs=0.005)
    # 2023 sans versement affichée à 0 : l'histogramme ne saute pas d'année
    assert b["by_year"].bars == [{"label": "2022", "value": 7.0}, {"label": "2023", "value": 0.0},
                                 {"label": "2024", "value": 32.0}]
    tte = next(r for r in b["by_line"].rows if r["symbol"] == "TTE")
    assert (tte["name"], tte["total"], tte["count"], tte["last"]) == ("TotalEnergies", 24, 3, "2024-06-15")
    assert tte["yoc"] == pytest.approx(17 / 500 * 100)  # 8 + 9 sur 12 mois / 500 €
    assert b["recent"].rows[0]["date"] == "2024-07-01"  # plus récent en premier


def test_dividendes_portefeuille_vide_et_sans_versement():
    assert "empty" in blocks(run("dividends", Portfolio(), EMPTY))
    pf = Portfolio(transactions=[tx("2024-01-02", "buy", "CW8", 1, 400)])
    assert "empty" in blocks(run("dividends", pf, EMPTY))


def test_dividende_en_devise_converti_au_taux_du_jour():
    pf = Portfolio(transactions=[
        tx("2023-05-02", "buy", "AAPL", 10, 150, currency="USD"),   # 1 500 $ × 0,90 = 1 350 €
        tx("2023-08-10", "dividend", "AAPL", currency="USD", amount=10),   # 10 $ × 0,90 = 9 €
        tx("2024-08-12", "dividend", "AAPL", currency="USD", amount=10),   # 10 $ × 0,80 = 8 €
    ])
    b = blocks(run("dividends", pf, usd_market(), {"as_of": "2024-12-31"}))
    assert b["total"].value == pytest.approx(17)
    assert b["last_12m"].value == pytest.approx(8)
    assert b["yield_on_cost"].value == pytest.approx(8 / 1350 * 100, abs=0.005)


def test_dividende_ligne_vendue_sans_rendement_sur_cout():
    pf = Portfolio(transactions=[
        tx("2024-01-02", "buy", "BNP", 5, 60),
        tx("2024-05-20", "dividend", "BNP", amount=23),
        tx("2024-06-01", "sell", "BNP", 5, 65),
    ])
    b = blocks(run("dividends", pf, EMPTY, {"as_of": "2024-12-31"}))
    assert b["by_line"].rows[0]["yoc"] is None   # plus détenue : pas de prix de revient
    assert b["yield_on_cost"].value is None


# --------------------------------------------------------------------------- Plus-values
def test_plus_values_prix_moyen_pondere():
    pf = Portfolio(transactions=[
        tx("2023-01-10", "buy", "CW8", 10, 100, fees=2),   # 1 002 €
        tx("2023-06-10", "buy", "CW8", 10, 120, fees=2),   # 1 202 € -> PMPA = 2 204 / 20 = 110,20 €
        tx("2023-09-01", "sell", "CW8", 5, 130, fees=1),   # cession 649 € ; revient 5 × 110,20 = 551 € ; +98 €
        tx("2024-02-01", "sell", "CW8", 5, 100, fees=1),   # cession 499 € ; revient 551 € ; −52 €
        tx("2024-03-01", "buy", "AIR", 2, 150),
        tx("2024-11-01", "sell", "AIR", 2, 160),           # cession 320 € ; revient 300 € ; +20 €
    ])
    b = blocks(run("capital_gains", pf, EMPTY, {"as_of": "2024-12-31"}))
    assert b["realized"].value == 66                    # 98 − 52 + 20
    assert b["realized_year"].value == -32                  # 2024 : −52 + 20
    assert (b["gains"].value, b["losses"].value) == (118, -52)
    assert b["by_year"].bars == [{"label": "2023", "value": 98.0}, {"label": "2024", "value": -32.0}]
    y2024 = b["years"].rows[0]
    assert y2024 == {"year": "2024", "count": 2, "proceeds": 819.0, "cost": 851.0, "pnl": -32.0}
    first = b["sales"].rows[-1]                          # plus ancienne cession en dernier
    assert (first["date"], first["proceeds"], first["cost"], first["pnl"]) == ("2023-09-01", 649, 551, 98)
    assert first["pnl_pct"] == pytest.approx(98 / 551 * 100, abs=0.005)


def test_plus_values_vide_une_ligne_et_division():
    assert "empty" in blocks(run("capital_gains", Portfolio(), EMPTY))
    assert "empty" in blocks(run("capital_gains", Portfolio(transactions=[tx("2024-01-02", "buy", "X", 1, 10)]), EMPTY))
    # Division par 4 : 10 titres à 400 € deviennent 40 titres à 100 € ; vente de 40 à 110 € -> +400 €
    pf = Portfolio(transactions=[
        tx("2024-01-02", "buy", "NVDA", 10, 400),
        tx("2024-06-10", "split", "NVDA", 4),
        tx("2024-07-01", "sell", "NVDA", 40, 110),
    ])
    b = blocks(run("capital_gains", pf, EMPTY, {"as_of": "2024-12-31"}))
    assert b["realized"].value == 400


def test_plus_value_en_devise():
    # Achat 10 × 150 $ à 0,90 = 1 350 € ; vente 10 × 200 $ à 0,80 = 1 600 € -> +250 € (et non +500 $ × taux)
    pf = Portfolio(transactions=[tx("2023-05-02", "buy", "AAPL", 10, 150, currency="USD"),
                                 tx("2024-05-02", "sell", "AAPL", 10, 200, currency="USD")])
    b = blocks(run("capital_gains", pf, usd_market(), {"as_of": "2024-12-31"}))
    assert b["realized"].value == pytest.approx(250)


def test_somme_au_centime_sans_erreur_binaire():
    # Trois cessions à +0,10 € ; en flottants 0.1 + 0.1 + 0.1 = 0.30000000000000004
    pf = Portfolio(transactions=[tx("2024-01-02", "buy", "X", 3, 1)] +
                   [tx("2024-02-0%d" % d, "sell", "X", 1, 1.1) for d in (1, 2, 3)])
    assert blocks(run("capital_gains", pf, EMPTY, {"as_of": "2024-12-31"}))["realized"].value == 0.3


def test_crypto_signalee():
    pf = Portfolio(transactions=[tx("2024-01-02", "buy", "BTC", 1, 100), tx("2024-02-02", "sell", "BTC", 1, 90)],
                   instruments={"BTC": Instrument(symbol="BTC", asset_class="crypto")})
    assert "crypto" in blocks(run("capital_gains", pf, EMPTY))
