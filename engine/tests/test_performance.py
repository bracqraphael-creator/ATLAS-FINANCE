"""Module Performance et calculs associés : valeurs attendues calculées à la main."""

import pandas as pd
import pytest

from atlas.core.analytics import daily_book, equivalent_value, twr_returns, value_history, xirr
from atlas.core.market import MarketData
from atlas.core.models import Instrument, Portfolio
from atlas.core.registry import run
from tests.conftest import tx


def blocks(result):
    return {b.id: b for b in result.blocks}


def market(closes: dict[str, list[float]], start="2024-01-01", bench: list[float] | None = None, fx=None):
    idx = pd.bdate_range(start, periods=len(next(iter(closes.values()))))
    md = MarketData(closes={s: pd.Series(v, index=idx) for s, v in closes.items()},
                    currencies={s: "EUR" for s in closes}, fx=fx or {}, source="test")
    if bench:
        md.benchmark = ("Indice test", pd.Series(bench, index=idx))
    return md


# Trois séances : lundi 01/01, mardi 02/01, mercredi 03/01/2024. X cote 100, 110, 99.
X = {"X": [100.0, 110.0, 99.0]}
PF = Portfolio(transactions=[tx("2024-01-01", "buy", "X", 10, 100),     # 1 000 € investis lundi
                             tx("2024-01-02", "buy", "X", 10, 110)])    # 1 100 € investis mardi, au cours du jour


def test_twr_l_argent_ajoute_n_est_pas_un_gain():
    book = daily_book(PF, market(X))
    assert book["value"].tolist() == [1000.0, 2200.0, 1980.0]
    assert book["flow"].tolist() == [1000.0, 1100.0, 0.0]
    r = twr_returns(book)
    # Lundi : acheté 100, clôture 100 -> 0 %. Mardi : les 10 premiers titres passent de 1 000 à 1 100 -> +10 %
    # (les 1 100 € ajoutés au cours du jour ne comptent pas). Mercredi : 2 200 -> 1 980 -> −10 %.
    assert r.tolist() == pytest.approx([0.0, 0.10, -0.10])
    # Chaînage : 1,10 × 0,90 − 1 = −1 %
    b = blocks(run("performance", PF, market(X)))
    assert b["twr"].value == pytest.approx(-1.0)
    assert b["gain"].value == pytest.approx(-120.0)          # 1 980 − 2 100
    assert b["annualized"].value is None                      # moins d'un an


def test_frais_dividendes_et_vente():
    pf = Portfolio(transactions=[
        tx("2024-01-01", "buy", "X", 10, 100, fees=10),       # 1 010 € investis, valeur de clôture 1 000
        tx("2024-01-02", "dividend", "X", amount=20),
        tx("2024-01-03", "sell", "X", 10, 99, fees=9),        # produit net 981 €
    ])
    book = daily_book(pf, market(X))
    assert book["flow"].tolist() == pytest.approx([1010.0, 0.0, -981.0])
    r = twr_returns(book)
    # Lundi : (1 000 − 1 010) / 1 010 ; mardi : (1 100 + 20 − 1 000) / 1 000 = +12 % ;
    # mercredi : tout vendu, (0 + 981 − 1 100) / 1 100
    assert r.tolist() == pytest.approx([-10 / 1010, 0.12, -119 / 1100])
    b = blocks(run("performance", pf, market(X)))
    assert b["gain"].value == pytest.approx(981 + 20 - 1010)  # −9 € : frais d'achat et de vente compris


def test_xirr_simple_et_cas_sans_solution():
    # 1 000 € versés, 1 100 € récupérés un an (365 jours) plus tard : 10 % par an
    assert xirr([(pd.Timestamp("2023-01-01"), -1000), (pd.Timestamp("2024-01-01"), 1100)]) == pytest.approx(0.10, abs=1e-6)
    assert xirr([(pd.Timestamp("2023-01-01"), -1000)]) is None


def test_comparaison_a_l_indice_meme_argent_memes_dates():
    # Indice : 50, 50, 55. Lundi 1 000 € -> 20 parts ; mardi 1 100 € -> 22 parts ; mercredi 42 × 55 = 2 310 €
    md = market(X, bench=[50.0, 50.0, 55.0])
    assert equivalent_value(daily_book(PF, md), md.benchmark[1]).iloc[-1] == pytest.approx(2310.0)
    b = blocks(run("performance", PF, md))
    assert b["bench"].value == pytest.approx(10.0)            # 50 -> 55
    assert b["pme"].value == pytest.approx(2310.0)
    assert "310,00 €" in b["pme-detail"].text
    year = b["years"].rows[0]
    assert (year["portfolio"], year["benchmark"], year["gap"]) == pytest.approx((-1.0, 10.0, -11.0))


def test_ligne_sans_cours_au_prix_de_revient_dans_la_courbe():
    # Y n'a pas de cours : comptée 500 € (prix de revient) chaque jour, comme dans la vue d'ensemble
    pf = Portfolio(transactions=PF.transactions + [tx("2024-01-01", "buy", "Y", 5, 100)])
    hist = value_history(pf, market(X))
    assert hist["value"].tolist() == [1500.0, 2700.0, 2480.0]
    assert hist["invested"].iloc[-1] == pytest.approx(2600.0)


def test_performance_vide_et_sans_cours():
    assert "empty" in blocks(run("performance", Portfolio(), market(X)))
    pf = Portfolio(transactions=[tx("2024-01-01", "buy", "Z", 1, 10)], instruments={"Z": Instrument(symbol="Z")})
    assert "no-prices" in blocks(run("performance", pf, market(X)))


def test_operation_le_week_end_rattachee_a_la_seance_suivante():
    pf = Portfolio(transactions=[tx("2023-12-30", "buy", "X", 10, 100)])   # samedi
    book = daily_book(pf, market(X))
    assert book.index[0] == pd.Timestamp("2024-01-01") or book["flow"].sum() == pytest.approx(1000.0)
    assert book["flow"].sum() == pytest.approx(1000.0)
