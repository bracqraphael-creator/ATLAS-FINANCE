"""Comparateur d'ETF : caractéristiques (fiches émetteurs) et mesures calculées sur les cours."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from importlib import resources
from typing import Any

import pandas as pd

from atlas.core.analytics import ledger_for, max_drawdown, points
from atlas.core.market import MarketData
from atlas.core.models import AssetClass, Portfolio
from atlas.core.result import Bars, ModuleResult, Note, Table, TimeSeries, fr_number

MAX_ETF = 6


@lru_cache(maxsize=1)
def reference() -> dict[str, Any]:
    return json.loads(resources.files("atlas").joinpath("data/etf_reference.json").read_text(encoding="utf-8"))


def lookup(symbol: str) -> dict[str, Any] | None:
    code = symbol.upper().split(".")[0]
    for etf in reference()["etfs"]:
        if etf["isin"] == symbol.upper() or code in etf["tickers"]:
            return etf
    return None


def _ann(growth: float, years: float) -> float:
    return (1 + growth) ** (1 / years) - 1


def _pct(x: float | None) -> float | None:
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(x * 100, 2)


def compute(portfolio: Portfolio, market: MarketData, params: dict[str, Any]) -> ModuleResult:
    result = ModuleResult(module_id="etf_compare", data_as_of=market.as_of)
    chosen = list(params.get("compare") or [])
    if not chosen:
        held = [p.symbol for p in ledger_for(portfolio, market).open_positions]
        chosen = [s for s in held if portfolio.instrument(s).asset_class in (AssetClass.ETF, AssetClass.COMMODITY)
                  or lookup(s)]
    chosen = list(dict.fromkeys(chosen))[:MAX_ETF]
    if not chosen:
        result.blocks.append(Note(id="empty", text=(
            "Aucun ETF dans ce portefeuille : indiquez des codes ISIN dans les réglages pour les comparer "
            "(par exemple IE00B4L5Y983, FR001400U5Q4).")))
        return result

    years = float(params.get("history_years") or 5)
    rows, curves, missing = [], {}, []
    for sym in chosen:
        ref = lookup(sym) or {}
        name = ref.get("name") or portfolio.instrument(sym).name or sym
        row: dict[str, Any] = {
            "name": name, "symbol": sym, "index": ref.get("index", "—"),
            "ter": ref.get("ter"), "replication": ref.get("replication", "—"),
            "pea": "oui" if ref.get("pea") else ("non" if ref else "—"),
            "distribution": ref.get("distribution", "—"),
        }
        if market.has(sym):
            close = market.close_base(sym).dropna()
            close = close[close.index >= close.index[-1] - pd.DateOffset(days=int(365.25 * years))]
            span = (close.index[-1] - close.index[0]).days / 365.25 if len(close) > 1 else 0
            last = close.iloc[-1]

            def back(y: float) -> float | None:
                if span < y - 0.02:
                    return None
                past = close[close.index <= close.index[-1] - pd.DateOffset(days=int(365.25 * y))]
                return float(last / past.iloc[-1] - 1) if not past.empty else None

            g1, g3, g5 = back(1), back(3), back(5)
            daily = close.pct_change().dropna()
            last_year = daily[daily.index >= daily.index[-1] - pd.DateOffset(days=365)]
            mdd, _ = max_drawdown(daily)
            row.update({
                "perf_1y": _pct(g1), "perf_3y": _pct(_ann(g3, 3) if g3 is not None else None),
                "perf_5y": _pct(_ann(g5, 5) if g5 is not None else None),
                "vol_1y": _pct(float(last_year.std() * math.sqrt(252)) if len(last_year) > 20 else None),
                "max_dd": _pct(-mdd), "history": round(span, 1),
            })
            curves[name] = close
        else:
            missing.append(name)
        rows.append(row)

    result.blocks.append(Table(
        id="compare", title="Comparaison",
        columns=[{"key": "name", "label": "ETF"}, {"key": "index", "label": "Indice"},
                 {"key": "ter", "label": "Frais courants", "unit": "%"}, {"key": "replication", "label": "Réplication"},
                 {"key": "pea", "label": "PEA"},
                 {"key": "perf_1y", "label": "Perf. 1 an", "unit": "%"}, {"key": "perf_3y", "label": "Perf. 3 ans /an", "unit": "%"},
                 {"key": "perf_5y", "label": "Perf. 5 ans /an", "unit": "%"}, {"key": "vol_1y", "label": "Volatilité 1 an", "unit": "%"},
                 {"key": "max_dd", "label": "Pire baisse", "unit": "%"}],
        rows=rows,
    ))

    with_ter = [r for r in rows if r["ter"] is not None]
    if with_ter:
        result.blocks.append(Bars(id="fees", title="Frais annuels pour 10 000 € investis", unit="EUR",
                                  bars=[{"label": r["name"][:28], "value": round(r["ter"] * 100, 2)} for r in with_ter]))

    if len(curves) >= 1:
        common = max(c.index[0] for c in curves.values())
        series = []
        for name, c in curves.items():
            c = c[c.index >= common]
            if len(c) > 1:
                series.append({"name": name[:40], "points": points(c / c.iloc[0] * 100)})
        if series:
            result.blocks.append(TimeSeries(id="growth", title=f"Évolution de 100 € depuis le {common.strftime('%d/%m/%Y')}",
                                            unit="", series=series))

    # Même indice, émetteurs différents : écarts de frais et de performance
    by_index: dict[str, list[dict]] = {}
    for r in rows:
        if r["index"] != "—":
            by_index.setdefault(r["index"], []).append(r)
    for idx, group in by_index.items():
        if len(group) > 1 and all(g.get("perf_1y") is not None for g in group):
            parts = ", ".join(f"{g['name']} : {fr_number(g['perf_1y'])} % sur 1 an, frais {fr_number(g['ter'])} %"
                              for g in group if g["ter"] is not None)
            result.blocks.append(Note(id=f"same-{idx}", text=f"Même indice ({idx}) : {parts}. L'écart de performance "
                                      "reflète les frais, la méthode de réplication et la devise de cotation."))
    if missing:
        result.blocks.append(Note(id="missing", level="warning", text=f"Cours indisponibles pour : {', '.join(missing)}."))
    unknown = [r["name"] for r in rows if r["ter"] is None]
    if unknown:
        result.blocks.append(Note(id="unknown", text=f"Caractéristiques non référencées pour : {', '.join(unknown)} "
                                  "(seules les mesures calculées sur les cours sont affichées)."))
    short = [f"{r['name']} ({fr_number(r['history'], 1)} an(s))" for r in rows if r.get("history") is not None and r["history"] < years - 0.1]
    if short:
        result.blocks.append(Note(id="short", text=f"Historique plus court que {fr_number(years, 0)} ans : {', '.join(short)}."))
    result.blocks.append(Note(id="source", text=reference()["_source"]))
    return result
