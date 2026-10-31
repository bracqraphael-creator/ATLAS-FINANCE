import pytest

from atlas.core.positions import build_ledger
from tests.conftest import tx


def test_prix_de_revient_moyen_et_plus_value_realisee():
    led = build_ledger([
        tx("2024-01-01", "buy", "X", 10, 100, fees=10),   # coût 1010 -> PRU 101
        tx("2024-02-01", "buy", "X", 10, 120),            # (1010 + 1200) / 20 = 110,5
        tx("2024-03-01", "sell", "X", 5, 130, fees=5),    # produit 645 - 5 × 110,5 = 92,5
    ])
    p = led.positions["X"]
    assert p.quantity == 15
    assert p.avg_cost == pytest.approx(110.5)
    assert p.realized_pnl_base == pytest.approx(92.5)


def test_division_d_action_conserve_le_capital_investi():
    led = build_ledger([tx("2024-01-01", "buy", "X", 10, 100), tx("2024-06-01", "split", "X", 2)])
    p = led.positions["X"]
    assert p.quantity == 20
    assert p.avg_cost == pytest.approx(50)
    assert p.cost_basis == pytest.approx(1000)


def test_vente_superieure_a_la_detention_est_limitee_et_signalee():
    led = build_ledger([tx("2024-01-01", "buy", "X", 2, 10), tx("2024-01-02", "sell", "X", 5, 12)])
    assert led.positions["X"].quantity == 0
    assert led.positions["X"].realized_pnl_base == pytest.approx(4)   # 2 × (12 - 10)
    assert led.warnings and "limitée" in led.warnings[0]


def test_conversion_en_devise_de_reference_au_taux_du_jour():
    led = build_ledger([tx("2024-01-01", "buy", "AAPL", 10, 100, currency="USD")], fx=lambda c, d: 0.9)
    p = led.positions["AAPL"]
    assert p.avg_cost == pytest.approx(100)
    assert p.avg_cost_base == pytest.approx(90)


def test_dividendes_frais_et_mouvements_de_cash():
    led = build_ledger([
        tx("2024-01-01", "deposit", amount=1000), tx("2024-01-02", "buy", "X", 1, 100),
        tx("2024-05-01", "dividend", "X", amount=3.5), tx("2024-06-01", "fee", amount=2),
        tx("2024-07-01", "withdrawal", amount=50),
    ])
    assert led.dividends_base == pytest.approx(3.5)
    assert led.fees_base == pytest.approx(2)
    assert led.deposits_base == 1000 and led.withdrawals_base == 50


def test_achat_et_vente_le_meme_jour_dans_le_bon_ordre():
    led = build_ledger([tx("2024-01-01", "sell", "X", 1, 110), tx("2024-01-01", "buy", "X", 1, 100)])
    assert led.positions["X"].realized_pnl_base == pytest.approx(10)
    assert not led.warnings


def test_portefeuille_vide():
    led = build_ledger([])
    assert led.open_positions == [] and led.realized_pnl_base == 0
