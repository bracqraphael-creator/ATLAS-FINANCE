"""Fournisseurs de données de marché.

- `DemoProvider` : prix FICTIFS générés de façon reproductible, pour développer sans clé API.
- `CsvProvider` : fichier CSV long (date, symbol, close, currency) ; les taux de change ont un symbole `FX:USD`.
- `EodhdProvider` : API EODHD (forfait personnel pour le prototype ; contrat commercial avant la vente).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import date
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from .market import MarketData


class DemoProvider:
    """Séries fictives (mouvement brownien géométrique), identiques à chaque appel."""

    # symbole : (devise, prix de départ, rendement annuel moyen, volatilité annuelle, lien au marché)
    UNIVERSE: dict[str, tuple[str, float, float, float, float]] = {
        "CW8": ("EUR", 350.0, 0.07, 0.15, 0.95),
        "PAEEM": ("EUR", 22.0, 0.05, 0.19, 0.70),
        "MC": ("EUR", 600.0, 0.06, 0.27, 0.65),
        "AAPL": ("USD", 130.0, 0.10, 0.29, 0.70),
        "BTC": ("EUR", 25000.0, 0.20, 0.65, 0.30),
    }

    def __init__(self, start: str = "2021-01-04", end: str = "2026-10-30") -> None:
        self.dates = pd.bdate_range(start, end)
        self._market = np.random.default_rng(self._seed("MARKET")).standard_normal(len(self.dates))

    @staticmethod
    def _seed(name: str) -> int:
        return int(hashlib.sha256(name.encode()).hexdigest()[:8], 16)

    def _path(self, name: str, start: float, mu: float, sigma: float, rho: float = 0.0) -> pd.Series:
        """rho = corrélation avec un facteur de marché commun, pour des corrélations réalistes."""
        own = np.random.default_rng(self._seed(name)).standard_normal(len(self.dates))
        z = rho * self._market + np.sqrt(1 - rho**2) * own
        dt = 1 / 252
        shocks = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * z
        shocks[0] = 0.0
        return pd.Series(start * np.exp(np.cumsum(shocks)), index=self.dates)

    def load(self, symbols: Iterable[str], base_currency: str = "EUR") -> MarketData:
        closes, currencies = {}, {}
        for s in symbols:
            if s in self.UNIVERSE:
                cur, p0, mu, sig, rho = self.UNIVERSE[s]
                closes[s] = self._path(s, p0, mu, sig, rho)
                currencies[s] = cur
        fx = {"USD": self._path("FX:USD", 0.82, 0.02, 0.07)}  # 1 USD en EUR
        return MarketData(closes, currencies, fx, base_currency, source="Données fictives de démonstration")


class CsvProvider:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self, symbols: Iterable[str], base_currency: str = "EUR") -> MarketData:
        df = pd.read_csv(self.path, parse_dates=["date"])
        wanted = set(symbols)
        closes, currencies, fx = {}, {}, {}
        for sym, g in df.groupby("symbol"):
            series = g.set_index("date")["close"]
            if str(sym).startswith("FX:"):
                fx[str(sym)[3:]] = series
            elif sym in wanted:
                closes[str(sym)] = series
                currencies[str(sym)] = str(g["currency"].iloc[-1]).upper()
        return MarketData(closes, currencies, fx, base_currency, source=f"Fichier {self.path.name}")


class EodhdProvider:
    """Clôtures ajustées via l'API EODHD. Symboles au format EODHD : `CW8.PA`, `AAPL.US`."""

    BASE_URL = "https://eodhd.com/api"

    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        if not api_key:
            raise ValueError("Clé API EODHD manquante (MARKET_DATA_API_KEY)")
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=30)

    def daily(self, symbol: str, start: date | None = None) -> pd.Series:
        params = {"api_token": self.api_key, "fmt": "json"}
        if start:
            params["from"] = start.isoformat()
        r = self.client.get(f"{self.BASE_URL}/eod/{symbol}", params=params)
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return pd.Series(dtype=float)
        df = pd.DataFrame(rows)
        col = "adjusted_close" if "adjusted_close" in df else "close"
        return pd.Series(df[col].astype(float).values, index=pd.to_datetime(df["date"]))

    def load(
        self,
        symbols: Iterable[str],
        currencies: dict[str, str],
        base_currency: str = "EUR",
        start: date | None = None,
    ) -> MarketData:
        closes = {s: self.daily(s, start) for s in symbols}
        fx = {}
        for cur in {c for c in currencies.values() if c != base_currency}:
            # Paire EODHD « USDEUR.FOREX » = prix d'1 USD en EUR
            fx[cur] = self.daily(f"{cur}{base_currency}.FOREX", start)
        return MarketData(closes, currencies, fx, base_currency, source="EODHD")
