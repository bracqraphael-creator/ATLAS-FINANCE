"""Rééquilibrage : écart à une répartition cible et répartition d'un versement (calcul arithmétique)."""

from __future__ import annotations

from typing import Any

from atlas.core.analytics import ledger_for
from atlas.core.market import MarketData
from atlas.core.models import Portfolio
from atlas.core.result import Bars, Kpi, ModuleResult, Note, Table, fr_number


def split_contribution(values: dict[str, float], targets: dict[str, float], amount: float) -> dict[str, float]:
    """Répartit `amount` sans vente : manques vers la cible (portefeuille + versement), au prorata s'ils
    dépassent le versement, surplus selon les poids cibles. `targets` : poids en fraction, somme = 1."""
    if amount <= 0:
        return {s: 0.0 for s in targets}
    total = sum(values.values()) + amount
    need = {s: max(w * total - values.get(s, 0.0), 0.0) for s, w in targets.items()}
    gap = sum(need.values())
    if gap <= 0:
        return {s: amount * w for s, w in targets.items()}
    if gap >= amount:
        return {s: amount * n / gap for s, n in need.items()}
    rest = amount - gap
    return {s: need[s] + rest * w for s, w in targets.items()}


def compute(portfolio: Portfolio, market: MarketData, params: dict[str, Any]) -> ModuleResult:
    result = ModuleResult(module_id="rebalance", data_as_of=market.as_of)
    led = ledger_for(portfolio, market)
    values = {p.symbol: (p.quantity * market.last_price_base(p.symbol) if market.has(p.symbol) else p.cost_basis_base)
              for p in led.open_positions}
    total = sum(values.values())
    if total <= 0 and not params.get("targets"):
        result.blocks.append(Note(id="empty", text="Aucune ligne détenue : définissez une répartition cible pour commencer."))
        return result

    raw = {s: w for s, w in (params.get("targets") or {}).items() if w > 0}
    defined = bool(raw)
    if not defined:   # pas de cible : la répartition actuelle sert de point de départ
        raw = {s: v / total * 100 for s, v in values.items()}
    weight_sum = sum(raw.values())
    targets = {s: w / weight_sum for s, w in raw.items()}
    name = lambda s: portfolio.instrument(s).name or s  # noqa: E731

    symbols = list(dict.fromkeys(list(targets) + list(values)))
    contribution = float(params.get("contribution") or 0)
    split = split_contribution(values, targets, contribution)
    rows = []
    for s in symbols:
        v, w = values.get(s, 0.0), targets.get(s, 0.0)
        cur = v / total if total > 0 else 0.0
        after = (v + split.get(s, 0.0)) / (total + contribution) if total + contribution > 0 else 0.0
        rows.append({
            "symbol": s, "name": name(s), "value": round(v, 2), "current": round(cur * 100, 2),
            "target": round(w * 100, 2), "drift_pts": round((cur - w) * 100, 2), "gap_eur": round(w * total - v, 2),
            "contribution": round(split.get(s, 0.0), 2), "after": round(after * 100, 2),
        })
    rows.sort(key=lambda r: -abs(r["drift_pts"]))
    drift = sum(abs(r["drift_pts"]) for r in rows) / 2

    result.blocks += [
        Kpi(id="total", label="Valeur du portefeuille", value=round(total, 2), unit="EUR"),
        Kpi(id="drift", label="Écart à la cible", value=round(drift, 2), unit="%",
            hint="part du portefeuille à déplacer pour l'atteindre"),
        Kpi(id="largest", label="Ligne la plus éloignée", value=rows[0]["drift_pts"] if rows else None, unit="%",
            hint=rows[0]["name"][:40] if rows else None),
    ]
    if contribution > 0:
        after_drift = sum(abs(r["after"] - r["target"]) for r in rows) / 2
        result.blocks.append(Kpi(id="drift_after", label="Écart après le versement", value=round(after_drift, 2), unit="%",
                                 hint=f"versement de {fr_number(contribution)} €"))
    result.blocks.append(Bars(id="gaps", title="Écart au poids cible (points)", unit="%",
                              bars=[{"label": r["name"][:24], "value": r["drift_pts"]} for r in rows]))
    cols = [{"key": "name", "label": "Ligne"}, {"key": "value", "label": "Valeur", "unit": "EUR"},
            {"key": "current", "label": "Poids actuel", "unit": "%"}, {"key": "target", "label": "Poids cible", "unit": "%"},
            {"key": "drift_pts", "label": "Écart (points)", "unit": "%"}, {"key": "gap_eur", "label": "Écart à combler", "unit": "EUR"}]
    if contribution > 0:
        cols += [{"key": "contribution", "label": "Part du versement", "unit": "EUR"},
                 {"key": "after", "label": "Poids après", "unit": "%"}]
    result.blocks.append(Table(id="lines", title="Répartition", columns=cols, rows=rows))
    if not defined:
        result.blocks.append(Note(id="no-target", level="warning", text=(
            "Aucune répartition cible définie : la répartition actuelle est affichée. Indiquez vos poids cibles "
            "dans les réglages pour mesurer l'écart.")))
    if abs(weight_sum - 100) > 0.01 and defined:
        result.blocks.append(Note(id="normalized", text=f"Poids cibles saisis : {fr_number(weight_sum)} % au total, ramenés à 100 %."))
    result.blocks.append(Note(id="nature", text=(
        "« Écart à combler » : montant qui sépare chaque ligne de son poids cible (négatif : ligne au-dessus de sa cible). "
        "Calcul arithmétique sur la cible que vous avez fixée.")))
    return result
