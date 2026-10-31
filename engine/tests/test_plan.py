"""Plan d'investissement : valeurs attendues calculées à la main."""

import pytest

from atlas.core.models import Portfolio
from atlas.core.registry import run
from atlas.modules.plan.compute import project
from tests.test_performance import market, X, PF


def blocks(result):
    return {b.id: b for b in result.blocks}


def test_versements_sans_rendement():
    values, paid = project(0, 100, 2, 0.0)
    assert values[-1] == pytest.approx(2400) and paid[-1] == pytest.approx(2400)


def test_capitalisation_mensuelle_formule_fermee():
    # 100 € par mois pendant 10 ans à 6 % par an : taux mensuel m = 1,06^(1/12) − 1,
    # valeur finale = 100 × ((1 + m)^120 − 1) / m (versements en fin de mois)
    m = 1.06 ** (1 / 12) - 1
    values, _ = project(0, 100, 10, 0.06)
    assert values[-1] == pytest.approx(100 * ((1 + m) ** 120 - 1) / m)
    # Capital seul : 1 000 € à 5 % pendant 3 ans -> 1 000 × 1,05³
    assert project(1000, 0, 3, 0.05)[0][-1] == pytest.approx(1000 * 1.05 ** 3)


def test_frais_et_hausse_des_versements():
    # Frais 1 % sur un rendement de 5 % : comme 4 % sans frais
    assert project(1000, 0, 5, 0.05, fees=0.01)[0][-1] == pytest.approx(1000 * 1.04 ** 5)
    # Versements de 100 € la 1re année, 110 € la 2e (hausse de 10 %), sans rendement : 1 200 + 1 320
    assert project(0, 100, 2, 0.0, increase=0.10)[1][-1] == pytest.approx(2520)


def test_module_plan_scenarios_et_inflation():
    params = {"monthly": 100, "years": 10, "initial": 0, "return_low": 0, "return_mid": 6, "return_high": 8,
              "fees": 0, "increase": 0, "inflation": 2}
    b = blocks(run("plan", Portfolio(), market(X), params))
    m = 1.06 ** (1 / 12) - 1
    central = 100 * ((1 + m) ** 120 - 1) / m
    assert b["final_mid"].value == pytest.approx(central, abs=0.01)
    assert b["final_low"].value == pytest.approx(12000)              # 0 % : la somme des versements
    assert b["paid"].value == pytest.approx(12000)
    assert b["real_mid"].value == pytest.approx(central / 1.02 ** 10, abs=0.01)
    assert b["final_low"].value < b["final_mid"].value < b["final_high"].value
    assert [r["year"] for r in b["milestones"].rows] == ["1 an", "5 ans", "10 ans"]
    assert "not-guaranteed" in b and "rendements constants" in b["hypotheses"].text


def test_capital_de_depart_vide_valeur_du_portefeuille():
    # PF vaut 20 × 99 = 1 980 € à la dernière clôture : c'est le capital de départ quand le champ est vide
    params = {"monthly": 0, "years": 1, "initial": None, "return_low": 0, "return_mid": 0, "return_high": 0,
              "fees": 0, "increase": 0, "inflation": 0}
    assert blocks(run("plan", PF, market(X), params))["final_mid"].value == pytest.approx(1980)


def test_parametre_invalide_refuse():
    with pytest.raises(ValueError):
        run("plan", Portfolio(), market(X), {"years": 80})
