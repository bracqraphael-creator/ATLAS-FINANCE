"""Fournisseurs de données de marché.

- `DemoProvider` : prix FICTIFS générés de façon reproductible, pour développer sans clé API.
- `CsvProvider` : fichier CSV long (date, symbol, close, currency) ; les taux de change ont un symbole `FX:USD`.
- `EodhdProvider` : API EODHD (forfait personnel pour le prototype ; contrat commercial avant la vente).
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
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


ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")
CRYPTO_ISIN_RE = re.compile(r"^XF000([A-Z]+?)\d{3,4}$")   # Trade Republic : XF000BTC0017 -> BTC

# Places préférées selon la devise de l'opération (codes EODHD)
EXCHANGES_BY_CURRENCY = {
    "EUR": ["PA", "XETRA", "AS", "BR", "MI", "MC", "LS", "F", "VI", "HE", "IR", "STU", "BE", "MU", "DU", "HM"],
    "USD": ["US"],
    "GBP": ["LSE"],
    "CHF": ["SW"],
    "CAD": ["TO", "V"],
}
EXCLUDED_EXCHANGES = {"EUFUND"}   # valeurs liquidatives de fonds : pas de clôtures quotidiennes fiables


class EodhdProvider:
    """Clôtures quotidiennes via l'API EODHD.

    Les symboles du portefeuille sont ceux des imports : code ISIN (cas courant), code EODHD (« CW8.PA »),
    ou crypto Trade Republic (« XF000BTC0017 »). Chaque symbole est résolu une fois en cotation EODHD :
    recherche par ISIN, puis choix de la place dont la devise est celle des opérations (une action américaine
    achetée en euros est valorisée sur une place européenne ou en dollars converti, au choix disponible).
    Résolutions et séries sont gardées en mémoire (6 h) : passer d'un module à l'autre ne rappelle pas l'API.

    Prix retenu : clôture brute (« close »), cohérente avec les quantités issues des opérations (les divisions
    d'actions sont des opérations à part entière). Les cotations en pence (GBX) sont converties en livres.
    """

    BASE_URL = "https://eodhd.com/api"
    TTL_SECONDS = 6 * 3600
    _resolved: dict[tuple[str, str], tuple[float, tuple[str, str] | None]] = {}
    _series: dict[str, tuple[float, date | None, pd.Series]] = {}
    _lock = threading.Lock()

    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        if not api_key:
            raise ValueError("Clé API EODHD manquante (MARKET_DATA_API_KEY)")
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=20)
        self.errors: list[str] = []

    @classmethod
    def clear_cache(cls) -> None:
        with cls._lock:
            cls._resolved.clear()
            cls._series.clear()

    # -- appels bruts ----------------------------------------------------------
    def _get(self, path: str, **params: str) -> object:
        r = self.client.get(f"{self.BASE_URL}/{path}", params={"api_token": self.api_key, "fmt": "json", **params})
        r.raise_for_status()
        return r.json()

    def daily(self, code: str, start: date | None = None) -> pd.Series:
        """Clôtures brutes d'une cotation EODHD, avec cache mémoire."""
        now = time.time()
        with self._lock:
            hit = self._series.get(code)
        if hit and now - hit[0] < self.TTL_SECONDS and (hit[1] is None or (start and hit[1] <= start)):
            return hit[2]
        rows = self._get(f"eod/{code}", **({"from": start.isoformat()} if start else {}))
        if not rows:
            series = pd.Series(dtype=float)
        else:
            df = pd.DataFrame(rows)
            series = pd.Series(df["close"].astype(float).values, index=pd.to_datetime(df["date"]))
        with self._lock:
            self._series[code] = (now, start, series)
        return series

    # -- résolution -------------------------------------------------------------
    def resolve(self, symbol: str, currency: str, base_currency: str = "EUR") -> tuple[str, str] | None:
        """Symbole du portefeuille -> (cotation EODHD, devise de cotation), ou None si introuvable."""
        if symbol.endswith("-TR"):            # lignes « en montants » (crypto sans quantité, Private Markets)
            return None
        crypto = CRYPTO_ISIN_RE.match(symbol)
        if crypto:
            return f"{crypto.group(1)}-{base_currency}.CC", base_currency
        if "." in symbol and not ISIN_RE.match(symbol):   # déjà au format EODHD
            return symbol, currency
        key = (symbol, currency)
        now = time.time()
        with self._lock:
            hit = self._resolved.get(key)
        if hit and (hit[1] is not None or now - hit[0] < 24 * 3600):
            return hit[1]
        found = self._search(symbol, currency)
        with self._lock:
            self._resolved[key] = (now, found)
        return found

    def _search(self, symbol: str, currency: str) -> tuple[str, str] | None:
        results = self._get(f"search/{symbol}", limit="50") or []
        is_isin = bool(ISIN_RE.match(symbol))
        preferred = EXCHANGES_BY_CURRENCY.get(currency, [])
        best: tuple[tuple, tuple[str, str]] | None = None
        for r in results if isinstance(results, list) else []:
            code, exchange = r.get("Code"), r.get("Exchange")
            if not code or not exchange or exchange in EXCLUDED_EXCHANGES:
                continue
            if is_isin and (r.get("ISIN") or "").upper() != symbol:
                continue
            if not is_isin and code.upper() != symbol.upper():
                continue
            cur = (r.get("Currency") or "").upper()
            rank = (
                cur == currency or (cur == "GBX" and currency == "GBP"),          # même devise que les opérations
                -(preferred.index(exchange) if exchange in preferred else 99),   # place préférée
                bool(r.get("isPrimary")),
                exchange == "US",                                                # repli : cotation principale US
            )
            candidate = (f"{code}.{exchange}", cur or currency)
            if best is None or rank > best[0]:
                best = (rank, candidate)
        return best[1] if best else None

    # -- chargement ---------------------------------------------------------------
    def load(
        self,
        symbols: Iterable[str],
        currencies: dict[str, str],
        base_currency: str = "EUR",
        start: date | None = None,
    ) -> MarketData:
        """`currencies` : devise des opérations de chaque symbole (sert à choisir la place)."""
        symbols = list(symbols)

        def fetch(sym: str) -> tuple[str, tuple[str, str] | None, pd.Series | None]:
            try:
                listing = self.resolve(sym, currencies.get(sym, base_currency), base_currency)
                if listing is None:
                    return sym, None, None
                return sym, listing, self.daily(listing[0], start)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                self.errors.append(f"{sym} : {exc}")
                return sym, None, None

        closes, quote_cur, listings = {}, {}, {}
        with ThreadPoolExecutor(max_workers=8) as pool:
            for sym, listing, series in pool.map(fetch, symbols):
                if listing is None or series is None or series.empty:
                    continue
                code, cur = listing
                if cur == "GBX":                  # pence -> livres
                    series, cur = series / 100.0, "GBP"
                closes[sym], quote_cur[sym], listings[sym] = series, cur, code

        fx = {}
        for cur in sorted({c for c in quote_cur.values() if c != base_currency}):
            try:
                # Paire EODHD « USDEUR.FOREX » = prix d'1 USD en EUR
                fx[cur] = self.daily(f"{cur}{base_currency}.FOREX", start)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                self.errors.append(f"taux {cur}/{base_currency} : {exc}")
                for sym in [s for s, c in quote_cur.items() if c == cur]:   # sans taux, pas de valorisation juste
                    closes.pop(sym, None)
                    quote_cur.pop(sym, None)
                    listings.pop(sym, None)
        return MarketData(closes, quote_cur, fx, base_currency, source="EODHD, clôtures quotidiennes",
                          listings=listings)
