"""Plus et moins-values réalisées : par année civile et par cession (prix moyen pondéré d'acquisition)."""

from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from atlas.core.analytics import ledger_for
from atlas.core.market import MarketData
from atlas.core.models import AssetClass, Portfolio
from atlas.core.result import Bars, Kpi, ModuleResult, Note, Table
from atlas.modules.dividends.compute import reference_date

CENT = Decimal("0.01")


def _d(x: float) -> Decimal:
    """Float -> Decimal sans artefact binaire (0.1 + 0.2), avant somme et arrondi au centime."""
    return Decimal(repr(x))


def _cents(x: Decimal) -> float:
    return float(x.quantize(CENT, rounding=ROUND_HALF_UP))


def compute(portfolio: Portfolio, market: MarketData, params: dict[str, Any]) -> ModuleResult:
    as_of = reference_date(portfolio, market, params)
    result = ModuleResult(module_id="capital_gains", data_as_of=as_of)
    led = ledger_for(portfolio, market)
    sales = led.realized

    if not sales:
        result.blocks.append(Note(id="empty", text="Aucune vente enregistrée : pas de plus-value réalisée."))
        return result

    total = sum((_d(s.pnl_base) for s in sales), Decimal(0))
    gains = sum((_d(s.pnl_base) for s in sales if s.pnl_base > 0), Decimal(0))
    losses = sum((_d(s.pnl_base) for s in sales if s.pnl_base < 0), Decimal(0))
    year = as_of.year if as_of else max(s.date.year for s in sales)
    this_year = sum((_d(s.pnl_base) for s in sales if s.date.year == year), Decimal(0))

    result.blocks += [
        Kpi(id="realized", label="Résultat net réalisé", value=_cents(total), unit="EUR", hint=f"{len(sales)} cession(s)"),
        Kpi(id="realized_year", label=f"Année {year}", value=_cents(this_year), unit="EUR"),
        Kpi(id="gains", label="Cessions en plus-value", value=_cents(gains), unit="EUR"),
        Kpi(id="losses", label="Cessions en moins-value", value=_cents(losses), unit="EUR"),
    ]

    by_year: dict[int, dict[str, Decimal | int]] = defaultdict(
        lambda: {"count": 0, "proceeds": Decimal(0), "cost": Decimal(0), "pnl": Decimal(0)})
    for s in sales:
        y = by_year[s.date.year]
        y["count"] += 1
        y["proceeds"] += _d(s.proceeds_base)
        y["cost"] += _d(s.cost_base)
        y["pnl"] += _d(s.pnl_base)
    years = range(min(by_year), max(by_year) + 1)
    result.blocks.append(Bars(id="by_year", title="Résultat net réalisé par année", unit="EUR",
                              bars=[{"label": str(y), "value": _cents(by_year[y]["pnl"]) if y in by_year else 0.0}
                                    for y in years]))
    result.blocks.append(Table(
        id="years", title="Par année civile",
        columns=[{"key": "year", "label": "Année"}, {"key": "count", "label": "Cessions"},
                 {"key": "proceeds", "label": "Prix de cession", "unit": "EUR"},
                 {"key": "cost", "label": "Prix de revient", "unit": "EUR"},
                 {"key": "pnl", "label": "Résultat net", "unit": "EUR"}],
        rows=[{"year": str(y), "count": v["count"], "proceeds": _cents(v["proceeds"]), "cost": _cents(v["cost"]),
               "pnl": _cents(v["pnl"])} for y, v in sorted(by_year.items(), reverse=True)],
    ))

    detail = [{
        "date": s.date.isoformat(),
        "name": portfolio.instrument(s.symbol).name or s.symbol,
        "quantity": round(s.quantity, 6),
        "proceeds": round(s.proceeds_base, 2),
        "cost": round(s.cost_base, 2),
        "pnl": round(s.pnl_base, 2),
        "pnl_pct": round(s.pnl_base / s.cost_base * 100, 2) if s.cost_base > 0 else None,
    } for s in reversed(sales)]
    result.blocks.append(Table(
        id="sales", title="Détail des cessions",
        columns=[{"key": "date", "label": "Date", "unit": "date"}, {"key": "name", "label": "Ligne"},
                 {"key": "quantity", "label": "Quantité"}, {"key": "proceeds", "label": "Prix de cession", "unit": "EUR"},
                 {"key": "cost", "label": "Prix de revient", "unit": "EUR"}, {"key": "pnl", "label": "Résultat", "unit": "EUR"},
                 {"key": "pnl_pct", "label": "Résultat", "unit": "%"}],
        rows=detail,
    ))

    if any(portfolio.instrument(s.symbol).asset_class == AssetClass.CRYPTO for s in sales):
        result.blocks.append(Note(id="crypto", level="warning", text=(
            "Des crypto-actifs figurent parmi les cessions. En France, ils relèvent d'un régime distinct "
            "(prix total d'acquisition de l'ensemble du portefeuille de crypto-actifs) : les montants ci-dessus, "
            "calculés ligne par ligne, ne correspondent pas à ce calcul.")))
    result.blocks.append(Note(id="wrapper", text=(
        "Dans un PEA, les cessions ne sont pas imposées au fil de l'eau : seul un retrait déclenche l'imposition "
        "du gain global du plan. Dans un compte-titres, plus et moins-values d'une même année se compensent.")))
    for i, w in enumerate(led.warnings):
        result.blocks.append(Note(id=f"ledger-{i}", level="warning", text=w))
    return result
