from __future__ import annotations

from typing import Any

from atlas.core.analytics import ledger_for, points, value_history
from atlas.core.market import MarketData
from atlas.core.models import Portfolio
from atlas.core.result import fr_number, Kpi, ModuleResult, Note, Table, TimeSeries


def compute(portfolio: Portfolio, market: MarketData, params: dict[str, Any]) -> ModuleResult:  # noqa: ARG001
    result = ModuleResult(module_id="overview", data_as_of=market.as_of)
    led = ledger_for(portfolio, market)
    open_pos = led.open_positions

    if not open_pos and not portfolio.transactions:
        result.blocks.append(Note(id="empty", text="Aucune opération pour l'instant : importez un fichier pour commencer."))
        return result

    rows, total_value, total_cost, missing = [], 0.0, 0.0, []
    for p in open_pos:
        inst = portfolio.instrument(p.symbol)
        if market.has(p.symbol):
            price, _ = market.last_price(p.symbol)
            value = p.quantity * market.last_price_base(p.symbol)
        else:
            price, value = None, p.cost_basis_base      # valorisé au PRU faute de cours
            missing.append(p.symbol)
        cost = p.cost_basis_base
        total_value += value
        total_cost += cost
        rows.append({
            "symbol": p.symbol,
            "name": inst.name or p.symbol,
            "quantity": round(p.quantity, 6),
            "avg_cost": round(p.avg_cost, 4),
            "price": None if price is None else round(price, 4),
            "currency": p.currency,
            "value": round(value, 2),
            "pnl": round(value - cost, 2),
            "pnl_pct": round((value / cost - 1) * 100, 2) if cost > 0 else None,
        })
    for r in rows:
        r["weight"] = round(r["value"] / total_value * 100, 2) if total_value > 0 else 0.0
    rows.sort(key=lambda r: r["value"], reverse=True)

    unrealized = total_value - total_cost
    realized = led.realized_pnl_base
    dividends = led.dividends_base
    total_gain = unrealized + realized + dividends - led.fees_base

    result.blocks += [
        Kpi(id="value", label="Valeur du portefeuille", value=round(total_value, 2), unit="EUR"),
        Kpi(id="invested", label="Capital investi (lignes ouvertes)", value=round(total_cost, 2), unit="EUR"),
        Kpi(id="unrealized", label="Plus-value latente", value=round(unrealized, 2), unit="EUR",
            hint=f"{'+' if unrealized >= 0 else '−'}{fr_number(abs(unrealized / total_cost * 100))} %" if total_cost > 0 else None),
        Kpi(id="realized", label="Plus-values réalisées", value=round(realized, 2), unit="EUR"),
        Kpi(id="dividends", label="Dividendes reçus", value=round(dividends, 2), unit="EUR"),
        Kpi(id="fees", label="Frais hors achats", value=round(led.fees_base, 2), unit="EUR"),
        Kpi(id="total_gain", label="Gain total", value=round(total_gain, 2), unit="EUR",
            hint="latent + réalisé + dividendes − frais"),
        Table(
            id="positions", title="Positions",
            columns=[
                {"key": "name", "label": "Ligne"}, {"key": "quantity", "label": "Quantité"},
                {"key": "avg_cost", "label": "PRU", "unit": "devise"}, {"key": "price", "label": "Cours", "unit": "devise"},
                {"key": "value", "label": "Valeur", "unit": "EUR"}, {"key": "pnl", "label": "+/- value", "unit": "EUR"},
                {"key": "pnl_pct", "label": "+/- value", "unit": "%"}, {"key": "weight", "label": "Poids", "unit": "%"},
            ],
            rows=rows,
        ),
    ]

    hist = value_history(portfolio, market)
    if len(hist) > 1:
        result.blocks.append(TimeSeries(
            id="history", title="Valeur et capital investi", unit="EUR",
            series=[{"name": "Valeur", "points": points(hist["value"])},
                    {"name": "Capital investi", "points": points(hist["invested"])}],
        ))

    if missing:
        result.blocks.append(Note(id="missing-prices", level="warning",
                                  text=f"Cours indisponible pour {', '.join(missing)} : ligne(s) valorisée(s) au prix de revient."))
    for i, w in enumerate(led.warnings):
        result.blocks.append(Note(id=f"ledger-{i}", level="warning", text=w))
    if market.source:
        result.blocks.append(Note(id="source", text=f"Source des cours : {market.source}."))
    return result
