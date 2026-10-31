"""Modèles de données du moteur : transactions, instruments, portefeuille."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class TransactionType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    FEE = "fee"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    SPLIT = "split"


class AssetClass(str, Enum):
    EQUITY = "equity"
    ETF = "etf"
    BOND = "bond"
    CRYPTO = "crypto"
    CASH = "cash"
    FUND = "fund"
    COMMODITY = "commodity"
    OTHER = "other"


class Transaction(BaseModel):
    """Une opération. Les transactions sont la seule source de vérité du portefeuille.

    - buy / sell : quantity > 0, price = prix unitaire dans `currency`, fees en plus.
    - dividend / fee / deposit / withdrawal : `amount` (positif) dans `currency`.
    - split : `quantity` = ratio (2 pour une division par deux du prix).
    """

    date: date
    type: TransactionType
    symbol: str | None = None
    name: str | None = None
    quantity: float = 0.0
    price: float = 0.0
    currency: str = "EUR"
    fees: float = 0.0
    amount: float | None = None

    @field_validator("currency")
    @classmethod
    def _upper(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 3:
            raise ValueError("devise sur 3 lettres attendue (EUR, USD…)")
        return v

    @field_validator("quantity", "price", "fees")
    @classmethod
    def _non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("valeur négative interdite")
        return v


class Instrument(BaseModel):
    """Métadonnées d'un actif, utilisées par les modules d'exposition."""

    symbol: str
    name: str | None = None
    asset_class: AssetClass = AssetClass.OTHER
    currency: str = "EUR"
    country: str | None = None
    sector: str | None = None


class Portfolio(BaseModel):
    name: str = "Portefeuille"
    base_currency: str = "EUR"
    transactions: list[Transaction] = Field(default_factory=list)
    instruments: dict[str, Instrument] = Field(default_factory=dict)

    def instrument(self, symbol: str) -> Instrument:
        return self.instruments.get(symbol) or Instrument(symbol=symbol)
