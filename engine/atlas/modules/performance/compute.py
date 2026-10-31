"""Performance : rendement pondéré dans le temps, rendement personnel (TRI), comparaison à un indice."""

from __future__ import annotations

from typing import Any

import pandas as pd

from atlas.core.analytics import daily_book, equivalent_value, points, twr_returns, xirr
from atlas.core.market import MarketData
from atlas.core.models import Portfolio
from atlas.core.result import Bars, Kpi, ModuleResult, Note, Table, TimeSeries, fr_number


def _pct(x: float | None) -> float | None:
    return None if x is None or pd.isna(x) else round(x * 100, 2)


def _growth(r: pd.Series) -> float:
    return float((1 + r).prod() - 1) if len(r) else 0.0


def compute(portfolio: Portfolio, market: MarketData, params: dict[str, Any]) -> ModuleResult:  # noqa: ARG001
    result = ModuleResult(module_id="performance", data_as_of=market.as_of)
    if not any(t.type.value == "buy" for t in portfolio.transactions):
        result.blocks.append(Note(id="empty", text="Aucun achat enregistré : la performance ne peut pas être calculée."))
        return result

    book = daily_book(portfolio, market)
    if not any(t.symbol and market.has(t.symbol) for t in portfolio.transactions):
        result.blocks.append(Note(id="no-prices", level="warning", text=(
            "Aucun cours disponible pour vos lignes : elles sont comptées à leur prix de revient et la performance "
            "affichée se limite aux revenus et aux frais.")))
    rets = twr_returns(book)
    first, last = book.index[0], book.index[-1]
    days = (last - first).days
    twr = _growth(rets)
    years = days / 365.25
    ann = (1 + twr) ** (1 / years) - 1 if years >= 1 else None

    value = float(book["value"].iloc[-1])
    income = float(book["income"].sum())
    net_invested = float(book["flow"].sum() + book["fees"].sum())
    gain = value + income - net_invested

    flows = [(d, -(r["flow"] + r["fees"]) + r["income"]) for d, r in book.iterrows()]
    flows.append((last, value))
    irr = xirr(flows) if years >= 1 / 12 else None

    ytd = rets[rets.index.year == last.year]
    result.blocks += [
        Kpi(id="twr", label="Performance depuis le début", value=_pct(twr), unit="%",
            hint=f"depuis le {first.strftime('%d/%m/%Y')}"),
        Kpi(id="annualized", label="Performance annualisée", value=_pct(ann), unit="%",
            hint=None if ann is not None else "moins d'un an d'historique"),
        Kpi(id="irr", label="Rendement personnel annuel (TRI)", value=_pct(irr), unit="%",
            hint="tient compte du moment de vos versements"),
        Kpi(id="ytd", label=f"Depuis le 1er janvier {last.year}", value=_pct(_growth(ytd)), unit="%"),
        Kpi(id="gain", label="Gain net", value=round(gain, 2), unit="EUR",
            hint="valeur + revenus − argent investi net"),
    ]

    wealth = (1 + rets).cumprod() * 100
    series = [{"name": "Vos placements", "points": points(wealth)}]
    bench_rets = None
    if market.benchmark is not None:
        name, bench = market.benchmark
        bench = bench.reindex(bench.index.union(book.index)).sort_index().ffill().reindex(book.index)
        if bench.notna().any():
            bench = bench.bfill()
            bench_rets = bench.pct_change().fillna(0.0)
            series.append({"name": name, "points": points(bench / bench.iloc[0] * 100)})
            pme = equivalent_value(book, bench)
            pme_value = float(pme.iloc[-1]) if not pd.isna(pme.iloc[-1]) else None
            bench_twr = _growth(bench_rets)
            result.blocks.append(Kpi(id="bench", label=f"{name.split(' (')[0]}, même période", value=_pct(bench_twr),
                                     unit="%", hint="indice de comparaison"))
            if pme_value is not None:
                ours = value + income
                result.blocks.append(Kpi(id="pme", label="Même argent placé dans l'indice", value=round(pme_value, 2),
                                         unit="EUR", hint=f"vos placements + revenus : {fr_number(ours)} €"))
                result.blocks.append(Note(id="pme-detail", text=(
                    f"Vos placements valent {fr_number(value)} € et vous ont versé {fr_number(income)} € de revenus, "
                    f"soit {fr_number(ours)} €. Le même argent, aux mêmes dates, placé dans l'indice de comparaison "
                    f"vaudrait {fr_number(pme_value)} € ({'+' if ours - pme_value >= 0 else '−'}"
                    f"{fr_number(abs(ours - pme_value))} € d'écart).")))
    result.blocks.append(TimeSeries(id="growth", title="Évolution de 100 € (base 100)", unit="", series=series))

    yearly = []
    for year in sorted(set(rets.index.year)):
        r = rets[rets.index.year == year]
        row = {"year": str(year), "portfolio": _pct(_growth(r))}
        if bench_rets is not None:
            b = _growth(bench_rets[bench_rets.index.year == year])
            row["benchmark"], row["gap"] = _pct(b), _pct(_growth(r) - b)
        row["partial"] = "oui" if (year == first.year and first.dayofyear > 7) or year == last.year else ""
        yearly.append(row)
    result.blocks.append(Bars(id="by_year", title="Performance par année", unit="%",
                              bars=[{"label": y["year"], "value": y["portfolio"] or 0.0} for y in yearly]))
    cols = [{"key": "year", "label": "Année"}, {"key": "portfolio", "label": "Vos placements", "unit": "%"}]
    if bench_rets is not None:
        cols += [{"key": "benchmark", "label": "Indice", "unit": "%"}, {"key": "gap", "label": "Écart", "unit": "%"}]
    cols.append({"key": "partial", "label": "Année incomplète"})
    result.blocks.append(Table(id="years", title="Par année civile", columns=cols, rows=list(reversed(yearly))))

    if days < 90:
        result.blocks.append(Note(id="short", level="warning", text=(
            f"Historique court ({days} jours) : la performance peut varier fortement d'une semaine à l'autre.")))
    if market.source:
        result.blocks.append(Note(id="source", text=f"Source des cours : {market.source}."))
    return result
