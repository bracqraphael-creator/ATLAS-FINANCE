"""Données de marché vues par les modules.

`MarketData` est un instantané en mémoire (prix de clôture quotidiens + taux de change) ;
les fournisseurs (`providers.py`) le construisent. Les modules ne font jamais d'appel réseau.
"""

from __future__ import annotations

from datetime import date

import pandas as pd


class MarketData:
    def __init__(
        self,
        closes: dict[str, pd.Series] | None = None,
        currencies: dict[str, str] | None = None,
        fx: dict[str, pd.Series] | None = None,
        base_currency: str = "EUR",
        source: str = "",
        listings: dict[str, str] | None = None,
    ) -> None:
        """
        closes : symbole -> série de clôtures (index = dates, devise de cotation).
        currencies : symbole -> devise de cotation.
        fx : devise -> série « 1 unité de devise = x unités de base » (ex. USD -> 0,92).
        """
        self.closes = {s: self._clean(v) for s, v in (closes or {}).items()}
        self.currencies = currencies or {}
        self.fx = {c: self._clean(v) for c, v in (fx or {}).items()}
        self.base_currency = base_currency
        self.source = source
        self.diagnostics: list[str] = []
        self.benchmark: tuple[str, pd.Series] | None = None   # (nom, clôtures en devise de référence)   # remarques du fournisseur (titres introuvables, candidats écartés)
        self.listings = listings or {}   # symbole du portefeuille -> cotation utilisée (ex. ISIN -> « CW8.PA »)

    @staticmethod
    def _clean(series: pd.Series) -> pd.Series:
        s = series.dropna().astype(float).copy()
        s.index = pd.to_datetime(s.index).normalize()
        return s.sort_index()[~s.index.duplicated(keep="last")]

    # -- taux de change ------------------------------------------------------
    def fx_rate(self, currency: str, on: date) -> float:
        if currency == self.base_currency:
            return 1.0
        series = self.fx.get(currency)
        if series is None or series.empty:
            raise KeyError(f"Taux de change {currency}/{self.base_currency} indisponible")
        ts = pd.Timestamp(on)
        past = series[series.index <= ts]
        return float(past.iloc[-1] if not past.empty else series.iloc[0])

    # -- prix ------------------------------------------------------------------
    def has(self, symbol: str) -> bool:
        return symbol in self.closes and not self.closes[symbol].empty

    def close_base(self, symbol: str) -> pd.Series:
        """Clôtures converties dans la devise de référence."""
        s = self.closes[symbol]
        cur = self.currencies.get(symbol, self.base_currency)
        if cur == self.base_currency:
            return s
        fx = self.fx.get(cur)
        if fx is None:
            raise KeyError(f"Taux de change {cur}/{self.base_currency} indisponible pour {symbol}")
        aligned = fx.reindex(s.index.union(fx.index)).ffill().bfill().reindex(s.index)
        return s * aligned

    def last_price(self, symbol: str) -> tuple[float, date]:
        s = self.closes[symbol]
        return float(s.iloc[-1]), s.index[-1].date()

    def last_price_base(self, symbol: str) -> float:
        return float(self.close_base(symbol).iloc[-1])

    @property
    def as_of(self) -> date | None:
        ends = [s.index[-1] for s in self.closes.values() if not s.empty]
        return max(ends).date() if ends else None
