from datetime import date

import pandas as pd
import pytest

from atlas.core.market import MarketData
from atlas.core.models import Transaction


def tx(d, type_, symbol=None, quantity=0.0, price=0.0, currency="EUR", fees=0.0, amount=None):
    return Transaction(date=date.fromisoformat(d), type=type_, symbol=symbol, quantity=quantity,
                       price=price, currency=currency, fees=fees, amount=amount)


@pytest.fixture
def simple_market():
    """CW8 passe de 100 à 120 en euros ; AAPL vaut 200 USD, 1 USD = 0,90 EUR."""
    idx = pd.bdate_range("2024-01-01", periods=5)
    return MarketData(
        closes={"CW8": pd.Series([100, 105, 110, 115, 120], index=idx),
                "AAPL": pd.Series([200] * 5, index=idx)},
        currencies={"CW8": "EUR", "AAPL": "USD"},
        fx={"USD": pd.Series([0.9] * 5, index=idx)},
        source="test",
    )


@pytest.fixture(autouse=True)
def no_network_provider(monkeypatch):
    """Aucun test n'appelle un vrai fournisseur de cours : cours fictifs sauf si un test choisit autrement."""
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "demo")
