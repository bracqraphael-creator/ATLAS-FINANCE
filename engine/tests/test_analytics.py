import math

import pandas as pd
import pytest

from atlas.core.analytics import annualized_return, annualized_vol, max_drawdown, regain_needed, value_history
from atlas.core.models import Portfolio
from tests.conftest import tx


def test_pire_baisse_sur_une_serie_connue():
    prices = pd.Series([100, 120, 90, 108])
    mdd, curve = max_drawdown(prices.pct_change().dropna())
    assert mdd == pytest.approx(0.25)          # 120 -> 90
    assert curve.min() == pytest.approx(-0.25)


@pytest.mark.parametrize("dd,needed", [(0.10, 0.1111), (0.25, 0.3333), (0.50, 1.0)])
def test_gain_necessaire_pour_rattraper_une_baisse(dd, needed):
    assert regain_needed(dd) == pytest.approx(needed, abs=1e-4)


def test_perte_totale():
    assert math.isinf(regain_needed(1.0))


def test_volatilite_nulle_si_rendement_constant():
    assert annualized_vol(pd.Series([0.001] * 100)) == pytest.approx(0)


def test_rendement_annualise():
    daily = 1.10 ** (1 / 252) - 1
    assert annualized_return(pd.Series([daily] * 252)) == pytest.approx(0.10)


def test_historique_de_valeur(simple_market):
    pf = Portfolio(transactions=[tx("2024-01-01", "buy", "CW8", 10, 100), tx("2024-01-03", "buy", "CW8", 10, 110)])
    hist = value_history(pf, simple_market)
    assert hist["value"].tolist() == [1000, 1050, 2200, 2300, 2400]
    assert hist["invested"].tolist() == [1000, 1000, 2100, 2100, 2100]
