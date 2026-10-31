from __future__ import annotations

from collections import defaultdict
from typing import Any

from atlas.core.analytics import ledger_for
from atlas.core.market import MarketData
from atlas.core.models import Portfolio
from atlas.core.result import Allocation, ModuleResult, Note, fr_number

CLASS_LABELS = {
    "equity": "Actions", "etf": "ETF", "bond": "Obligations", "crypto": "Crypto", "cash": "Liquidités",
    "fund": "Fonds", "commodity": "Matières premières", "other": "Autres",
}
DIMENSIONS = [
    ("asset_class", "Par classe d'actif"),
    ("country", "Par pays ou zone"),
    ("sector", "Par secteur"),
    ("currency", "Par devise"),
    ("line", "Par ligne"),
]


def compute(portfolio: Portfolio, market: MarketData, params: dict[str, Any]) -> ModuleResult:  # noqa: ARG001
    result = ModuleResult(module_id="exposure", data_as_of=market.as_of)
    led = ledger_for(portfolio, market)

    values: dict[str, float] = {}
    for p in led.open_positions:
        values[p.symbol] = p.quantity * market.last_price_base(p.symbol) if market.has(p.symbol) else p.cost_basis_base
    total = sum(values.values())
    if total <= 0:
        result.blocks.append(Note(id="empty", text="Aucune position ouverte à répartir."))
        return result

    for dim, title in DIMENSIONS:
        buckets: dict[str, float] = defaultdict(float)
        for symbol, value in values.items():
            inst = portfolio.instrument(symbol)
            if dim == "asset_class":
                key = CLASS_LABELS[inst.asset_class.value]
            elif dim == "currency":
                key = market.currencies.get(symbol, inst.currency)
            elif dim == "line":
                key = inst.name or symbol
            else:
                key = getattr(inst, dim) or "Non renseigné"
            buckets[key] += value
        slices = sorted(
            ({"label": k, "value": round(v, 2), "weight": round(v / total, 6)} for k, v in buckets.items()),
            key=lambda s: s["value"], reverse=True,
        )
        result.blocks.append(Allocation(id=dim, title=title, slices=slices))

    top = max(values.values()) / total
    if top > 0.5:
        name = max(values, key=values.get)
        result.blocks.append(Note(id="concentration", level="warning",
                                  text=f"Une seule ligne ({portfolio.instrument(name).name or name}) représente {fr_number(top * 100, 0)} % du portefeuille."))
    if any(portfolio.instrument(s).asset_class.value == "etf" for s in values):
        result.blocks.append(Note(id="etf-lookthrough",
                                  text="Les ETF sont comptés selon leur zone déclarée. Le détail de leur contenu (pays, secteurs, sociétés) sera ajouté avec les données de composition."))
    return result
