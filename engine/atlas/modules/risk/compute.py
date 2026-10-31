from __future__ import annotations

import math
from typing import Any

from atlas.core.analytics import (
    annualized_return, annualized_vol, current_weights, downside_vol, line_returns,
    max_drawdown, points, ratio, regain_needed, replay_returns,
)
from atlas.core.market import MarketData
from atlas.core.models import Portfolio
from atlas.core.result import fr_number, Kpi, ModuleResult, Note, Table, TimeSeries

MIN_OBSERVATIONS = 60  # environ trois mois de séances


def _pct(x: float | None, digits: int = 2) -> float | None:
    return None if x is None or math.isinf(x) else round(x * 100, digits)


def compute(portfolio: Portfolio, market: MarketData, params: dict[str, Any]) -> ModuleResult:
    result = ModuleResult(module_id="risk", data_as_of=market.as_of)
    weights = current_weights(portfolio, market)
    if weights.empty:
        result.blocks.append(Note(id="empty", text="Aucune position valorisable : le risque ne peut pas être calculé."))
        return result

    rets = line_returns(list(weights.index), market, params["lookback_years"])
    if len(rets) < MIN_OBSERVATIONS:
        result.blocks.append(Note(id="short-history", level="warning",
                                  text=f"Historique trop court ({len(rets)} séances, minimum {MIN_OBSERVATIONS}) pour des statistiques fiables."))
        return result

    port = replay_returns(weights, rets)
    rf = params["risk_free_rate"] / 100   # saisi en %
    ann_ret, vol, dvol = annualized_return(port), annualized_vol(port), downside_vol(port)
    mdd, dd_curve = max_drawdown(port)

    result.blocks += [
        Kpi(id="volatility", label="Volatilité annualisée", value=_pct(vol), unit="%"),
        Kpi(id="max_drawdown", label="Pire baisse", value=_pct(-mdd), unit="%",
            hint=f"il faut {fr_number(regain_needed(mdd) * 100)} % de hausse pour la rattraper"),
        Kpi(id="annual_return", label="Rendement annualisé (rejoué)", value=_pct(ann_ret), unit="%"),
        Kpi(id="sharpe", label="Ratio de Sharpe", value=None if (s := ratio(ann_ret - rf, vol)) is None else round(s, 2)),
        Kpi(id="sortino", label="Ratio de Sortino", value=None if (s := ratio(ann_ret - rf, dvol)) is None else round(s, 2)),
        Kpi(id="worst_day", label="Pire séance", value=_pct(float(port.min())), unit="%"),
        Kpi(id="best_day", label="Meilleure séance", value=_pct(float(port.max())), unit="%"),
        TimeSeries(id="drawdown", title="Baisse depuis le plus haut", unit="%",
                   series=[{"name": "Drawdown", "points": points(dd_curve * 100)}]),
    ]

    line_rows = []
    for sym in weights.sort_values(ascending=False).index:
        l_mdd, _ = max_drawdown(rets[sym])
        line_rows.append({
            "name": portfolio.instrument(sym).name or sym,
            "weight": _pct(float(weights[sym])),
            "volatility": _pct(annualized_vol(rets[sym])),
            "max_drawdown": _pct(-l_mdd),
            "contribution": _pct(float(weights[sym] * rets[sym].std() * rets.corrwith(port)[sym] / port.std()))
            if port.std() > 0 else None,
        })
    result.blocks.append(Table(
        id="lines", title="Risque par ligne",
        columns=[{"key": "name", "label": "Ligne"}, {"key": "weight", "label": "Poids", "unit": "%"},
                 {"key": "volatility", "label": "Volatilité", "unit": "%"},
                 {"key": "max_drawdown", "label": "Pire baisse", "unit": "%"},
                 {"key": "contribution", "label": "Part du risque", "unit": "%"}],
        rows=line_rows,
    ))

    if len(weights) > 1:
        corr = rets.corr()
        names = {s: portfolio.instrument(s).name or s for s in corr.columns}
        result.blocks.append(Table(
            id="correlations", title="Corrélations entre lignes",
            columns=[{"key": "name", "label": ""}] + [{"key": s, "label": names[s]} for s in corr.columns],
            rows=[{"name": names[a], **{b: round(float(corr.loc[a, b]), 2) for b in corr.columns}} for a in corr.index],
        ))

    result.blocks.append(Note(id="period", text=f"Période analysée : {rets.index[0].date():%d/%m/%Y} au {rets.index[-1].date():%d/%m/%Y} ({len(rets)} séances)."))
    if market.source:
        result.blocks.append(Note(id="source", text=f"Source des cours : {market.source}."))
    return result
