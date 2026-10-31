"""Plan d'investissement : projection de versements mensuels selon trois scénarios (non garantie)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from atlas.core.analytics import ledger_for
from atlas.core.market import MarketData
from atlas.core.models import Portfolio
from atlas.core.result import Kpi, ModuleResult, Note, Table, TimeSeries, fr_number


def project(initial: float, monthly: float, years: int, annual_return: float, fees: float = 0.0,
            increase: float = 0.0) -> tuple[list[float], list[float]]:
    """Valeur et versements cumulés en fin de chaque mois (taux en fraction : 0,05 = 5 %).

    Taux mensuel équivalent : (1 + rendement − frais)^(1/12) − 1 ; versement en fin de mois, augmenté de
    `increase` au début de chaque nouvelle année."""
    rate = (1 + annual_return - fees) ** (1 / 12) - 1
    value, paid, contribution = initial, initial, monthly
    values, paids = [], []
    for month in range(1, years * 12 + 1):
        if month > 1 and (month - 1) % 12 == 0:
            contribution *= 1 + increase
        value = value * (1 + rate) + contribution
        paid += contribution
        values.append(value)
        paids.append(paid)
    return values, paids


def _current_value(portfolio: Portfolio, market: MarketData) -> float:
    led = ledger_for(portfolio, market)
    total = 0.0
    for p in led.open_positions:
        total += p.quantity * market.last_price_base(p.symbol) if market.has(p.symbol) else p.cost_basis_base
    return total


def compute(portfolio: Portfolio, market: MarketData, params: dict[str, Any]) -> ModuleResult:
    start = market.as_of or date.today()
    result = ModuleResult(module_id="plan", data_as_of=market.as_of)
    years, monthly = int(params["years"]), float(params["monthly"])
    from_portfolio = params.get("initial") in (None, "")
    initial = _current_value(portfolio, market) if from_portfolio else float(params["initial"])
    pct = lambda k: float(params[k]) / 100  # noqa: E731
    fees, increase, inflation = pct("fees"), pct("increase"), pct("inflation")
    scenarios = [("Prudent", pct("return_low")), ("Central", pct("return_mid")), ("Favorable", pct("return_high"))]

    runs = {name: project(initial, monthly, years, r, fees, increase) for name, r in scenarios}
    paid = runs["Central"][1]
    final = {name: v[-1] for name, (v, _) in runs.items()}
    total_paid = paid[-1]
    real = final["Central"] / (1 + inflation) ** years

    result.blocks += [
        Kpi(id="final_mid", label=f"Valeur dans {years} ans, scénario central", value=round(final["Central"], 2), unit="EUR",
            hint=f"rendement {fr_number(pct('return_mid') * 100, 1)} % par an, frais déduits"),
        Kpi(id="paid", label="Total versé", value=round(total_paid, 2), unit="EUR",
            hint=f"dont {fr_number(initial)} € de départ" if initial else None),
        Kpi(id="gain_mid", label="Gains, scénario central", value=round(final["Central"] - total_paid, 2), unit="EUR"),
        Kpi(id="final_low", label="Scénario prudent", value=round(final["Prudent"], 2), unit="EUR",
            hint=f"{fr_number(pct('return_low') * 100, 1)} % par an"),
        Kpi(id="final_high", label="Scénario favorable", value=round(final["Favorable"], 2), unit="EUR",
            hint=f"{fr_number(pct('return_high') * 100, 1)} % par an"),
        Kpi(id="real_mid", label="Scénario central en euros d'aujourd'hui", value=round(real, 2), unit="EUR",
            hint=f"inflation supposée {fr_number(inflation * 100, 1)} % par an"),
    ]

    # Courbes mensuelles (échantillonnées au trimestre pour rester légères)
    dates = pd.date_range(pd.Timestamp(start) + pd.offsets.MonthEnd(1), periods=years * 12, freq="ME")
    keep = [i for i in range(len(dates)) if i % 3 == 2 or i == len(dates) - 1]
    series = [{"name": f"{name} ({fr_number(r * 100, 1)} %)", "points": [[dates[i].date().isoformat(), round(runs[name][0][i], 2)] for i in keep]}
              for name, r in reversed(scenarios)]
    series.append({"name": "Versements cumulés", "points": [[dates[i].date().isoformat(), round(paid[i], 2)] for i in keep]})
    result.blocks.append(TimeSeries(id="projection", title="Projection du capital", unit="EUR", series=series))

    milestones = sorted({y for y in (1, 5, 10, 15, 20, 25, 30, 40, 50) if y <= years} | {years})
    rows = []
    for y in milestones:
        i = y * 12 - 1
        rows.append({"year": f"{y} an{'s' if y > 1 else ''}", "paid": round(paid[i], 2),
                     "low": round(runs["Prudent"][0][i], 2), "mid": round(runs["Central"][0][i], 2),
                     "high": round(runs["Favorable"][0][i], 2)})
    result.blocks.append(Table(
        id="milestones", title="Étapes",
        columns=[{"key": "year", "label": "Horizon"}, {"key": "paid", "label": "Versé", "unit": "EUR"},
                 {"key": "low", "label": "Prudent", "unit": "EUR"}, {"key": "mid", "label": "Central", "unit": "EUR"},
                 {"key": "high", "label": "Favorable", "unit": "EUR"}],
        rows=rows,
    ))

    hyp = (f"Hypothèses : départ {fr_number(initial)} €"
           + (" (valeur actuelle du portefeuille)" if from_portfolio and initial else "")
           + f", {fr_number(monthly)} € par mois" + (f" augmentés de {fr_number(increase * 100, 1)} % par an" if increase else "")
           + f", {years} ans, frais {fr_number(fees * 100, 2)} % par an, rendements constants de "
           + ", ".join(f"{fr_number(r * 100, 1)} %" for _, r in scenarios) + " par an, avant impôts.")
    result.blocks += [
        Note(id="hypotheses", text=hyp),
        Note(id="not-guaranteed", level="warning", text=(
            "Projection non garantie : elle applique des rendements réguliers alors que les marchés alternent hausses "
            "et baisses, parfois fortes et durables. Le capital investi en actions peut baisser.")),
    ]
    return result
