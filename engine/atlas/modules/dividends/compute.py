"""Dividendes et coupons perçus : totaux, historique annuel, détail par ligne, rendement sur coût."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from atlas.core.analytics import ledger_for
from atlas.core.market import MarketData
from atlas.core.models import Portfolio
from atlas.core.result import Bars, Kpi, ModuleResult, Note, Table, fr_number


def reference_date(portfolio: Portfolio, market: MarketData, params: dict[str, Any]) -> date | None:
    """Date des données : paramètre explicite, sinon dernier cours connu ou dernière opération si plus récente."""
    if params.get("as_of"):
        return date.fromisoformat(str(params["as_of"]))
    candidates = [d for d in (market.as_of, max((t.date for t in portfolio.transactions), default=None)) if d]
    return max(candidates) if candidates else None


def compute(portfolio: Portfolio, market: MarketData, params: dict[str, Any]) -> ModuleResult:
    as_of = reference_date(portfolio, market, params)
    result = ModuleResult(module_id="dividends", data_as_of=as_of)
    led = ledger_for(portfolio, market)
    income = sorted(led.income, key=lambda i: i.date)

    if not income:
        result.blocks.append(Note(id="empty", text="Aucun dividende ni coupon enregistré dans ce portefeuille."))
        return result

    total = sum(i.amount_base for i in income)
    start_12m = as_of - timedelta(days=365) if as_of else None
    last_12m = sum(i.amount_base for i in income if start_12m and start_12m < i.date <= as_of)
    this_year = sum(i.amount_base for i in income if as_of and i.date.year == as_of.year)
    open_cost = sum(p.cost_basis_base for p in led.open_positions)
    yoc = last_12m / open_cost * 100 if open_cost > 0 else None

    result.blocks += [
        Kpi(id="total", label="Revenus perçus depuis le début", value=round(total, 2), unit="EUR",
            hint=f"{len(income)} versement(s)"),
        Kpi(id="last_12m", label="12 derniers mois", value=round(last_12m, 2), unit="EUR"),
        Kpi(id="this_year", label=f"Année {as_of.year}" if as_of else "Année en cours", value=round(this_year, 2), unit="EUR"),
        Kpi(id="yield_on_cost", label="Rendement sur coût (12 mois)", value=None if yoc is None else round(yoc, 2), unit="%",
            hint="revenus 12 mois / capital investi"),
    ]

    by_year: dict[int, float] = defaultdict(float)
    for i in income:
        by_year[i.date.year] += i.amount_base
    years = range(min(by_year), max(by_year) + 1)   # années sans versement affichées à 0
    result.blocks.append(Bars(id="by_year", title="Revenus par année", unit="EUR",
                              bars=[{"label": str(y), "value": round(by_year.get(y, 0.0), 2)} for y in years]))

    # Par ligne : total, versements, dernier versement, rendement sur coût si la ligne est encore détenue
    per: dict[str, dict[str, Any]] = {}
    for i in income:
        r = per.setdefault(i.symbol, {"total": 0.0, "count": 0, "last": i.date, "last_12m": 0.0})
        r["total"] += i.amount_base
        r["count"] += 1
        r["last"] = max(r["last"], i.date)
        if start_12m and start_12m < i.date <= as_of:
            r["last_12m"] += i.amount_base
    rows = []
    for symbol, r in per.items():
        pos = led.positions.get(symbol)
        cost = pos.cost_basis_base if pos and pos.quantity > 1e-12 else 0.0
        rows.append({
            "symbol": symbol,
            "name": portfolio.instrument(symbol).name or symbol,
            "total": round(r["total"], 2),
            "count": r["count"],
            "last": r["last"].isoformat(),
            "last_12m": round(r["last_12m"], 2),
            "yoc": round(r["last_12m"] / cost * 100, 2) if cost > 0 else None,
            "share": round(r["total"] / total * 100, 2) if total > 0 else 0.0,
        })
    rows.sort(key=lambda r: r["total"], reverse=True)
    result.blocks.append(Table(
        id="by_line", title="Par ligne",
        columns=[{"key": "name", "label": "Ligne"}, {"key": "total", "label": "Total perçu", "unit": "EUR"},
                 {"key": "count", "label": "Versements"}, {"key": "last", "label": "Dernier versement", "unit": "date"},
                 {"key": "last_12m", "label": "12 mois", "unit": "EUR"}, {"key": "yoc", "label": "Rdt sur coût", "unit": "%"},
                 {"key": "share", "label": "Part du total", "unit": "%"}],
        rows=rows,
    ))

    recent = [{"date": i.date.isoformat(), "name": portfolio.instrument(i.symbol).name or i.symbol,
               "amount": round(i.amount_base, 2)} for i in reversed(income[-20:])]
    result.blocks.append(Table(
        id="recent", title="Derniers versements",
        columns=[{"key": "date", "label": "Date", "unit": "date"}, {"key": "name", "label": "Ligne"},
                 {"key": "amount", "label": "Montant", "unit": "EUR"}],
        rows=recent,
    ))
    if yoc is not None and open_cost > 0:
        result.blocks.append(Note(id="yoc", text=(
            f"Sur les 12 mois précédant le {as_of.strftime('%d/%m/%Y')}, les revenus perçus représentent "
            f"{fr_number(yoc)} % du capital investi dans les lignes détenues ({fr_number(open_cost)} €).")))
    return result
