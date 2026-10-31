"""Calcul des positions à partir des transactions.

Méthode du prix de revient unitaire moyen pondéré (PRU), frais d'achat inclus :
c'est la méthode retenue par l'administration fiscale française pour les titres.
Les montants « base » sont convertis dans la devise de référence au taux du jour de l'opération.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date

from .models import Transaction, TransactionType

# fx(devise, date) -> nombre d'unités de devise de référence pour 1 unité de `devise`
FxFn = Callable[[str, date], float]


def _identity_fx(currency: str, on: date) -> float:  # noqa: ARG001
    return 1.0


@dataclass
class Position:
    symbol: str
    currency: str
    quantity: float = 0.0
    avg_cost: float = 0.0          # PRU en devise de cotation, frais inclus
    avg_cost_base: float = 0.0     # PRU en devise de référence
    realized_pnl_base: float = 0.0
    dividends_base: float = 0.0
    first_date: date | None = None

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_cost

    @property
    def cost_basis_base(self) -> float:
        return self.quantity * self.avg_cost_base


@dataclass
class Realized:
    """Une cession : quantité vendue, prix de cession net de frais, prix de revient (PRU) et résultat."""
    date: date
    symbol: str
    quantity: float
    proceeds_base: float
    cost_base: float

    @property
    def pnl_base(self) -> float:
        return self.proceeds_base - self.cost_base


@dataclass
class Income:
    date: date
    symbol: str
    amount_base: float


@dataclass
class Ledger:
    positions: dict[str, Position] = field(default_factory=dict)
    realized: list[Realized] = field(default_factory=list)   # cessions, dans l'ordre chronologique
    income: list[Income] = field(default_factory=list)       # dividendes et coupons
    fees_base: float = 0.0            # frais isolés (droits de garde, etc.)
    deposits_base: float = 0.0
    withdrawals_base: float = 0.0
    warnings: list[str] = field(default_factory=list)

    @property
    def open_positions(self) -> list[Position]:
        return [p for p in self.positions.values() if p.quantity > 1e-12]

    @property
    def realized_pnl_base(self) -> float:
        return sum(p.realized_pnl_base for p in self.positions.values())

    @property
    def dividends_base(self) -> float:
        return sum(p.dividends_base for p in self.positions.values())


def build_ledger(transactions: Iterable[Transaction], fx: FxFn | None = None) -> Ledger:
    fx = fx or _identity_fx
    ledger = Ledger()
    # Ordre stable : par date, achats avant ventes le même jour
    order = {TransactionType.SPLIT: 0, TransactionType.BUY: 1, TransactionType.SELL: 2}
    txs = sorted(transactions, key=lambda t: (t.date, order.get(t.type, 3)))

    for t in txs:
        rate = fx(t.currency, t.date)
        if t.type in (TransactionType.BUY, TransactionType.SELL, TransactionType.SPLIT, TransactionType.DIVIDEND):
            if not t.symbol:
                ledger.warnings.append(f"{t.date} : opération « {t.type.value} » sans symbole ignorée.")
                continue
            pos = ledger.positions.setdefault(t.symbol, Position(symbol=t.symbol, currency=t.currency))

        if t.type == TransactionType.BUY:
            if t.quantity <= 0:
                ledger.warnings.append(f"{t.date} : achat de {t.symbol} sans quantité ignoré.")
                continue
            cost = t.quantity * t.price + t.fees
            new_qty = pos.quantity + t.quantity
            pos.avg_cost = (pos.cost_basis + cost) / new_qty
            pos.avg_cost_base = (pos.cost_basis_base + cost * rate) / new_qty
            pos.quantity = new_qty
            pos.first_date = pos.first_date or t.date

        elif t.type == TransactionType.SELL:
            qty = t.quantity
            if qty > pos.quantity + 1e-9:
                ledger.warnings.append(
                    f"{t.date} : vente de {qty:g} {t.symbol} alors que {pos.quantity:g} sont détenus ; "
                    "vente limitée à la quantité détenue (historique d'import incomplet ?)."
                )
                qty = pos.quantity
            if qty <= 0:
                continue
            proceeds_base = (qty * t.price - t.fees) * rate
            cost_base = qty * pos.avg_cost_base
            pos.realized_pnl_base += proceeds_base - cost_base
            ledger.realized.append(Realized(t.date, t.symbol, qty, proceeds_base, cost_base))
            pos.quantity -= qty
            if pos.quantity <= 1e-12:
                pos.quantity = 0.0

        elif t.type == TransactionType.SPLIT:
            ratio = t.quantity
            if ratio <= 0:
                ledger.warnings.append(f"{t.date} : division de {t.symbol} sans ratio ignorée.")
                continue
            pos.quantity *= ratio
            pos.avg_cost /= ratio
            pos.avg_cost_base /= ratio

        elif t.type == TransactionType.DIVIDEND:
            pos.dividends_base += (t.amount or 0.0) * rate
            ledger.income.append(Income(t.date, t.symbol, (t.amount or 0.0) * rate))

        elif t.type == TransactionType.FEE:
            ledger.fees_base += (t.amount or 0.0) * rate
        elif t.type == TransactionType.DEPOSIT:
            ledger.deposits_base += (t.amount or 0.0) * rate
        elif t.type == TransactionType.WITHDRAWAL:
            ledger.withdrawals_base += (t.amount or 0.0) * rate

    return ledger


def holdings_on(transactions: Iterable[Transaction], on: date) -> dict[str, float]:
    """Quantités détenues à une date donnée (pour reconstruire l'historique de valeur)."""
    subset = [t for t in transactions if t.date <= on]
    return {p.symbol: p.quantity for p in build_ledger(subset).open_positions}
