import pytest

from atlas.api import demo_portfolio, load_market
from atlas.core.models import Instrument, Portfolio
from atlas.core.registry import registry, run
from atlas.core.result import DISCLAIMER
from tests.conftest import tx


def blocks(result):
    return {b.id: b for b in result.blocks}


def test_registre_decouvre_les_modules():
    assert {"overview", "exposure", "risk"} <= set(registry())


def test_vue_d_ensemble_valeurs_simples(simple_market):
    pf = Portfolio(transactions=[tx("2024-01-01", "buy", "CW8", 10, 100),
                                 tx("2024-01-01", "buy", "AAPL", 1, 200, currency="USD")])
    b = blocks(run("overview", pf, simple_market))
    # CW8 : 10 × 120 = 1200 ; AAPL : 200 USD × 0,90 = 180 EUR
    assert b["value"].value == pytest.approx(1380)
    assert b["invested"].value == pytest.approx(1180)   # 1000 + 200 × 0,90
    assert b["unrealized"].value == pytest.approx(200)
    assert sum(r["weight"] for r in b["positions"].rows) == pytest.approx(100, abs=0.02)


def test_vue_d_ensemble_portefeuille_vide(simple_market):
    b = blocks(run("overview", Portfolio(), simple_market))
    assert "empty" in b


def test_exposition_poids_somment_a_un(simple_market):
    pf = Portfolio(
        transactions=[tx("2024-01-01", "buy", "CW8", 10, 100), tx("2024-01-01", "buy", "AAPL", 1, 200, currency="USD")],
        instruments={"CW8": Instrument(symbol="CW8", asset_class="etf", country="Monde"),
                     "AAPL": Instrument(symbol="AAPL", asset_class="equity", currency="USD", country="États-Unis")},
    )
    b = blocks(run("exposure", pf, simple_market))
    for dim in ("asset_class", "country", "sector", "currency", "line"):
        assert sum(s["weight"] for s in b[dim].slices) == pytest.approx(1)
    assert {s["label"] for s in b["currency"].slices} == {"EUR", "USD"}
    assert b["sector"].slices[0]["label"] == "Non renseigné"
    assert "concentration" in b   # CW8 pèse 1200 / 1380 = 87 %


def test_risque_historique_trop_court(simple_market):
    pf = Portfolio(transactions=[tx("2024-01-01", "buy", "CW8", 10, 100)])
    assert "short-history" in blocks(run("risk", pf, simple_market))


def test_risque_sur_le_portefeuille_de_demonstration():
    pf = demo_portfolio()
    result = run("risk", pf, load_market(pf), {"lookback_years": 3})
    b = blocks(result)
    assert 0 < b["volatility"].value < 100
    assert b["max_drawdown"].value < 0
    assert sum(r["contribution"] for r in b["lines"].rows) == pytest.approx(100, abs=0.1)
    assert result.disclaimer == DISCLAIMER and result.method


def test_parametre_hors_bornes_refuse():
    pf = demo_portfolio()
    with pytest.raises(ValueError):
        run("risk", pf, load_market(pf), {"lookback_years": 50})


def test_tous_les_modules_tournent_sur_la_demo():
    pf = demo_portfolio()
    market = load_market(pf)
    for module_id in registry():
        result = run(module_id, pf, market)
        assert result.blocks, module_id
        assert result.data_as_of is not None


def test_aucun_texte_de_recommandation():
    """Règle de conformité : les modules décrivent, ils ne recommandent pas."""
    forbidden = ("achetez", "vendez", "nous recommandons", "le meilleur pour vous", "conseillons")
    pf = demo_portfolio()
    market = load_market(pf)
    for module_id, spec in registry().items():
        text = run(module_id, pf, market).model_dump_json().lower() + str(spec.texts).lower()
        assert not any(w in text for w in forbidden), module_id
