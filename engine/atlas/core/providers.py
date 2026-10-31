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


# Yahoo : code de place (champ « exchange » de la recherche) préféré selon la devise des opérations
YAHOO_EXCHANGES_BY_CURRENCY = {
    "EUR": ["PAR", "GER", "AMS", "MIL", "BRU", "MCE", "LIS", "FRA", "VIE", "HEL", "ISE", "STU", "BER", "MUN", "DUS", "HAM"],
    "USD": ["NMS", "NYQ", "NGM", "NCM", "ASE", "PCX", "BTS"],
    "GBP": ["LSE"],
    "CHF": ["EBS"],
    "CAD": ["TOR", "VAN"],
}
YAHOO_TYPES = {"EQUITY", "ETF", "MUTUALFUND", "CRYPTOCURRENCY"}


class YahooProvider:
    """Clôtures quotidiennes via les services publics de Yahoo Finance (gratuit, sans clé).

    Service non officiel, sans engagement de disponibilité, réservé à un usage personnel : il sert le
    prototype ; un fournisseur sous licence (EODHD…) prend le relais avant toute commercialisation.
    Même logique que EodhdProvider : résolution des ISIN en cotations (place choisie selon la devise des
    opérations), clôture brute, cotations en pence (GBp) converties en livres, cache mémoire 6 h, appels en
    parallèle, un titre introuvable n'arrête pas les autres.
    """

    SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
    CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AtlasFinance/0.1)", "Accept": "application/json"}
    TTL_SECONDS = 6 * 3600
    _resolved: dict[tuple[str, str], tuple[float, str | None]] = {}
    _series: dict[str, tuple[float, date | None, pd.Series, str]] = {}
    _lock = threading.Lock()

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(timeout=20, headers=self.HEADERS, follow_redirects=True)
        self.errors: list[str] = []
        self.trace: list[str] = []   # candidats examinés par le repli par le nom (diagnostic)

    @classmethod
    def clear_cache(cls) -> None:
        with cls._lock:
            cls._resolved.clear()
            cls._series.clear()

    # -- cours ---------------------------------------------------------------------
    def daily(self, ticker: str, start: date | None = None) -> tuple[pd.Series, str]:
        """(clôtures brutes, devise de cotation) d'un symbole Yahoo, avec cache mémoire."""
        now = time.time()
        with self._lock:
            hit = self._series.get(ticker)
        if hit and now - hit[0] < self.TTL_SECONDS and (hit[1] is None or (start and hit[1] <= start)):
            return hit[2], hit[3]
        begin = pd.Timestamp(start or date(2000, 1, 1)).tz_localize("UTC")
        params = {"period1": str(int(begin.timestamp())), "period2": str(int(now) + 86400),
                  "interval": "1d", "events": "split", "includeAdjustedClose": "false"}
        r = self.client.get(self.CHART_URL.format(symbol=ticker), params=params)
        r.raise_for_status()
        chart = (r.json().get("chart") or {})
        if chart.get("error") or not chart.get("result"):
            raise ValueError(f"cours indisponibles pour {ticker}")
        res = chart["result"][0]
        currency = (res.get("meta", {}).get("currency") or "").strip()
        stamps = res.get("timestamp") or []
        closes = ((res.get("indicators", {}).get("quote") or [{}])[0].get("close")) or []
        idx = pd.to_datetime(stamps, unit="s", utc=True).tz_convert(None).normalize()
        series = pd.Series(closes, index=idx, dtype=float).dropna()
        with self._lock:
            self._series[ticker] = (now, start, series, currency)
        return series, currency

    # -- résolution -------------------------------------------------------------------
    def resolve(self, symbol: str, currency: str, base_currency: str = "EUR") -> str | None:
        if symbol.endswith("-TR"):            # lignes « en montants » : jamais rattachées à un cours
            return None
        crypto = CRYPTO_ISIN_RE.match(symbol)
        if crypto:
            return f"{crypto.group(1)}-{base_currency}"
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

    def _search(self, symbol: str, currency: str) -> str | None:
        r = self.client.get(self.SEARCH_URL, params={"q": symbol, "quotesCount": "20", "newsCount": "0",
                                                    "listsCount": "0", "enableFuzzyQuery": "false"})
        r.raise_for_status()
        quotes = r.json().get("quotes") or []
        is_isin = bool(ISIN_RE.match(symbol))
        preferred = YAHOO_EXCHANGES_BY_CURRENCY.get(currency, [])
        usd = YAHOO_EXCHANGES_BY_CURRENCY["USD"]
        best: tuple[tuple, str] | None = None
        for q in quotes:
            ticker, exchange = q.get("symbol"), q.get("exchange")
            if not ticker or q.get("quoteType") not in YAHOO_TYPES:
                continue
            # Recherche par ticker (import CSV « CW8 ») : le symbole doit correspondre, place incluse ou non
            if not is_isin and ticker.split(".")[0].upper() != symbol.split(".")[0].upper():
                continue
            rank = (
                -(preferred.index(exchange) if exchange in preferred else 99),   # place de la devise des opérations
                exchange in usd,                                                # repli : cotation américaine
            )
            if best is None or rank > best[0]:
                best = (rank, ticker)
        return best[1] if best else None

    # -- repli par le nom, contrôlé par les prix réellement payés ------------------------
    def _fx_on(self, cur: str, base: str, on: date, start: date | None) -> float | None:
        if cur in (base, ""):
            return 1.0
        cur = "GBP" if cur in ("GBp", "GBX") else cur
        series, _ = self.daily(f"{cur}{base}=X", start)
        past = series[series.index <= pd.Timestamp(on)]
        return float(past.iloc[-1]) if not past.empty else None

    def _matches_trades(self, ticker: str, trades: list[tuple[date, float, str]], base: str,
                        start: date | None) -> bool:
        """Le cours du candidat, le jour des opérations, est-il à ±20 % des prix payés ?"""
        series, cur = self.daily(ticker, start)
        if series.empty:
            return False
        checked = 0
        for on, price, tx_cur in trades[:3]:
            past = series[series.index <= pd.Timestamp(on)]
            if past.empty or price <= 0:
                continue
            close = float(past.iloc[-1]) / (100.0 if cur in ("GBp", "GBX") else 1.0)
            to_base = self._fx_on(cur, base, on, start)
            tx_to_base = self._fx_on(tx_cur, base, on, start)
            if not to_base or not tx_to_base:
                continue
            ratio = close * to_base / (price * tx_to_base)
            self.trace.append(f"{ticker} {on} : cours {close:g} {cur}, payé {price:g} {tx_cur}, rapport {ratio:.2f}")
            if not 0.8 <= ratio <= 1.25:
                return False
            checked += 1
        return checked > 0

    def resolve_by_name(self, symbol: str, name: str, trades: list[tuple[date, float, str]],
                        base_currency: str, start: date | None) -> str | None:
        key = (symbol, "name")
        now = time.time()
        with self._lock:
            hit = self._resolved.get(key)
        if hit and (hit[1] is not None or now - hit[0] < 24 * 3600):
            return hit[1]
        # « SIEMENS AG NA », « CREDIT AGRICOLE INH. EO 3 » : mentions de forme et de nominal retirées
        query = re.sub(r"\b(INH|NA|O\.N|EO|DL|LS|SF|ADR|REG|CL|ACC|DIST)\b\.?|[-,]*\d[\d,./-]*", " ", name, flags=re.I)
        query = re.sub(r"\s+", " ", query).strip()
        found = None
        if len(query) >= 3 and trades:
            r = self.client.get(self.SEARCH_URL, params={"q": query, "quotesCount": "8", "newsCount": "0",
                                                        "listsCount": "0"})
            r.raise_for_status()
            quotes = (r.json().get("quotes") or [])[:6]
            self.trace.append(f"recherche « {query} » : " + ", ".join(
                f"{q.get('symbol')} ({q.get('quoteType')})" for q in quotes) if quotes else f"recherche « {query} » : aucun résultat")
            for q in quotes:
                ticker = q.get("symbol")
                if not ticker or q.get("quoteType") not in YAHOO_TYPES:
                    continue
                try:
                    if self._matches_trades(ticker, trades, base_currency, start):
                        found = ticker
                        break
                except (httpx.HTTPError, ValueError, KeyError) as exc:
                    self.trace.append(f"{ticker} : {exc}")
                    continue
        with self._lock:
            self._resolved[key] = (now, found)
        return found

    # -- chargement ----------------------------------------------------------------------
    def load(self, symbols: Iterable[str], currencies: dict[str, str], base_currency: str = "EUR",
             start: date | None = None,
             hints: dict[str, tuple[str, list[tuple[date, float, str]]]] | None = None) -> MarketData:
        """`hints` : symbole -> (nom du titre, opérations (date, prix, devise)) pour le repli par le nom."""
        symbols = list(symbols)
        hints = hints or {}

        def usable(sym: str, ticker: str | None) -> bool:
            """Cotation avec des cours, et vraisemblable au regard des prix payés quand on les connaît."""
            if ticker is None:
                return False
            try:
                series, _ = self.daily(ticker, start)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                self.trace.append(f"{sym} -> {ticker} : {exc}")
                return False
            if series.empty:
                self.trace.append(f"{sym} -> {ticker} : aucun cours")
                return False
            if sym in hints and hints[sym][1] and not CRYPTO_ISIN_RE.match(sym):
                if not self._matches_trades(ticker, hints[sym][1], base_currency, start):
                    self.trace.append(f"{sym} -> {ticker} : écarté, cours éloigné des prix payés")
                    return False
            return True

        def fetch(sym: str):
            try:
                ticker = self.resolve(sym, currencies.get(sym, base_currency), base_currency)
                if not usable(sym, ticker):
                    ticker = None
                    if sym in hints and not sym.endswith("-TR"):
                        name, trades = hints[sym]
                        candidate = self.resolve_by_name(sym, name, trades, base_currency, start)
                        ticker = candidate if usable(sym, candidate) else None
                if ticker is None:
                    return sym, None, None, None
                series, cur = self.daily(ticker, start)
                return sym, ticker, series, cur
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                self.errors.append(f"{sym} : {exc}")
                return sym, None, None, None

        closes, quote_cur, listings = {}, {}, {}
        with ThreadPoolExecutor(max_workers=6) as pool:
            for sym, ticker, series, cur in pool.map(fetch, symbols):
                if ticker is None or series is None or series.empty:
                    continue
                if cur in ("GBp", "GBX"):          # pence -> livres
                    series, cur = series / 100.0, "GBP"
                cur = (cur or base_currency).upper()
                closes[sym], quote_cur[sym], listings[sym] = series, cur, ticker

        fx = {}
        for cur in sorted({c for c in quote_cur.values() if c != base_currency}):
            try:
                fx[cur], _ = self.daily(f"{cur}{base_currency}=X", start)   # « USDEUR=X » : 1 USD en EUR
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                self.errors.append(f"taux {cur}/{base_currency} : {exc}")
                for sym in [s for s, c in quote_cur.items() if c == cur]:
                    closes.pop(sym, None)
                    quote_cur.pop(sym, None)
                    listings.pop(sym, None)
        md = MarketData(closes, quote_cur, fx, base_currency, source="Yahoo Finance, clôtures quotidiennes",
                        listings=listings)
        md.diagnostics = self.errors + self.trace
        return md
