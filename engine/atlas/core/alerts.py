"""Alertes : constater qu'un seuil a été franchi, jamais conseiller.

Une alerte se déclenche au FRANCHISSEMENT d'un seuil entre l'avant-dernière et la dernière clôture connues :
elle ne se répète pas chaque jour tant que la condition reste vraie. Fonctions pures (aucun appel réseau).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel

from .analytics import ledger_for, twr_returns, daily_book
from .market import MarketData
from .models import Portfolio
from .result import fr_number

AlertKind = Literal["line_move", "below_cost", "price_cross", "rsi", "drawdown"]
KIND_LABELS = {
    "line_move": "Variation d'une séance",
    "below_cost": "Passage sous le prix de revient",
    "price_cross": "Franchissement d'un cours",
    "rsi": "RSI 14 jours",
    "drawdown": "Baisse du portefeuille depuis son plus haut",
}


class AlertRule(BaseModel):
    id: str
    kind: AlertKind
    symbol: str | None = None          # None : toutes les lignes détenues (sauf price_cross et drawdown)
    threshold: float                    # %, cours ou niveau de RSI selon le type
    direction: Literal["above", "below", "both"] = "below"


class AlertEvent(BaseModel):
    rule_id: str
    key: str                            # identifiant de dédoublonnage : règle + titre + date
    date: date
    symbol: str | None
    value: float
    message: str


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI de Wilder : moyennes lissées (alpha = 1/période) des hausses et des baisses ; 100 si aucune baisse."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(loss != 0, 100.0).where(gain.notna())


def _crossed(prev: float, last: float, level: float, direction: str) -> str | None:
    if direction in ("above", "both") and prev <= level < last:
        return "above"
    if direction in ("below", "both") and prev >= level > last:
        return "below"
    return None


def _d(day: pd.Timestamp) -> str:
    return day.strftime("%d/%m/%Y")


def evaluate(portfolio: Portfolio, market: MarketData, rules: list[AlertRule]) -> list[AlertEvent]:
    led = ledger_for(portfolio, market)
    held = [p.symbol for p in led.open_positions]
    name = lambda s: portfolio.instrument(s).name or s  # noqa: E731
    events: list[AlertEvent] = []

    for rule in rules:
        if rule.kind == "drawdown":
            book = daily_book(portfolio, market)
            if len(book) < 3:
                continue
            wealth = (1 + twr_returns(book)).cumprod()
            dd = wealth / wealth.cummax() - 1
            level = -abs(rule.threshold) / 100
            prev, last = float(dd.iloc[-2]), float(dd.iloc[-1])
            if prev > level >= last:
                peak_day = wealth[: dd.index[-1]].idxmax()
                events.append(AlertEvent(
                    rule_id=rule.id, key=f"{rule.id}:portfolio:{dd.index[-1].date()}", date=dd.index[-1].date(),
                    symbol=None, value=round(last * 100, 2),
                    message=f"Le portefeuille est en baisse de {fr_number(-last * 100)} % depuis son plus haut "
                            f"du {_d(peak_day)} (seuil {fr_number(abs(rule.threshold))} %), au {_d(dd.index[-1])}."))
            continue

        targets = [rule.symbol] if rule.symbol else ([] if rule.kind == "price_cross" else held)
        for sym in targets:
            if not sym or not market.has(sym):
                continue
            close = market.closes[sym]
            if len(close) < 2:
                continue
            day, cur = close.index[-1], market.currencies.get(sym, market.base_currency)
            prev_c, last_c = float(close.iloc[-2]), float(close.iloc[-1])
            key = f"{rule.id}:{sym}:{day.date()}"

            if rule.kind == "line_move":
                move = last_c / prev_c - 1
                limit = abs(rule.threshold) / 100
                hit = (rule.direction in ("below", "both") and move <= -limit) or \
                      (rule.direction in ("above", "both") and move >= limit)
                if hit:
                    events.append(AlertEvent(
                        rule_id=rule.id, key=key, date=day.date(), symbol=sym, value=round(move * 100, 2),
                        message=f"{name(sym)} a varié de {'+' if move > 0 else '−'}{fr_number(abs(move) * 100)} % "
                                f"sur la séance du {_d(day)} (seuil {fr_number(abs(rule.threshold))} %)."))

            elif rule.kind == "below_cost":
                pos = led.positions.get(sym)
                if not pos or pos.quantity <= 1e-12 or pos.avg_cost <= 0:
                    continue
                level = pos.avg_cost * (1 - abs(rule.threshold) / 100)
                if prev_c >= level > last_c:
                    gap = last_c / pos.avg_cost - 1
                    events.append(AlertEvent(
                        rule_id=rule.id, key=key, date=day.date(), symbol=sym, value=round(gap * 100, 2),
                        message=f"{name(sym)} cote {fr_number(last_c)} {cur}, soit {fr_number(-gap * 100)} % sous "
                                f"votre prix de revient ({fr_number(pos.avg_cost)} {cur}), le {_d(day)}."))

            elif rule.kind == "price_cross":
                way = _crossed(prev_c, last_c, rule.threshold, rule.direction)
                if way:
                    events.append(AlertEvent(
                        rule_id=rule.id, key=key, date=day.date(), symbol=sym, value=round(last_c, 4),
                        message=f"Le cours de {name(sym)} est passé {'au-dessus' if way == 'above' else 'en dessous'} "
                                f"de {fr_number(rule.threshold)} {cur} ({fr_number(last_c)} {cur} le {_d(day)})."))

            elif rule.kind == "rsi":
                r = rsi(close).dropna()
                if len(r) < 2:
                    continue
                way = _crossed(float(r.iloc[-2]), float(r.iloc[-1]), rule.threshold, rule.direction)
                if way:
                    events.append(AlertEvent(
                        rule_id=rule.id, key=key, date=day.date(), symbol=sym, value=round(float(r.iloc[-1]), 1),
                        message=f"Le RSI 14 jours de {name(sym)} est passé {'au-dessus' if way == 'above' else 'en dessous'} "
                                f"de {fr_number(rule.threshold, 0)} ({fr_number(float(r.iloc[-1]), 1)}) le {_d(day)}."))
    return events
