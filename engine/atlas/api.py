"""API HTTP du moteur de calcul."""

from __future__ import annotations

import json
import os
from datetime import timedelta
from importlib import resources
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import __version__
from .core.importers import Analysis, ImportResult, analyze_file, parse_file
from .core.market import MarketData
from .core.models import Instrument, Portfolio, Transaction
from .core.providers import DemoProvider, EodhdProvider, YahooProvider
from .core.registry import registry, run
from .core.result import ModuleResult

MAX_UPLOAD_BYTES = 5 * 1024 * 1024

app = FastAPI(title="ATLAS FINANCE — moteur de calcul", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _provider_name() -> str:
    """Fournisseur de cours : « yahoo » (gratuit, par défaut), « eodhd » (sous licence, clé requise), « demo »."""
    return os.environ.get("MARKET_DATA_PROVIDER", "yahoo").lower()


def load_market(portfolio: Portfolio, demo: bool = False) -> MarketData:
    """Cours pour un portefeuille. La démonstration garde ses cours fictifs, quel que soit le fournisseur."""
    symbols = sorted({t.symbol for t in portfolio.transactions if t.symbol})
    provider = _provider_name()
    if demo or provider == "demo":
        return DemoProvider().load(symbols, portfolio.base_currency)
    # Devise des opérations de chaque titre : elle oriente le choix de la place de cotation
    tx_currency: dict[str, str] = {}
    for t in portfolio.transactions:
        if t.symbol and t.type.value in ("buy", "sell"):
            tx_currency.setdefault(t.symbol, t.currency)
    start = min((t.date for t in portfolio.transactions), default=None)
    if start:
        start -= timedelta(days=10)   # quelques séances avant la première opération
    if provider == "eodhd":
        key = os.environ.get("MARKET_DATA_API_KEY", "")
        if not key:
            return MarketData(base_currency=portfolio.base_currency, source="clé EODHD manquante")
        return EodhdProvider(key).load(symbols, tx_currency, portfolio.base_currency, start)
    # Indices pour le repli par le nom : nom du titre et ses achats (prix payés), contrôle de vraisemblance
    hints: dict[str, tuple[str, list]] = {}
    for t in portfolio.transactions:
        if t.symbol and t.type.value == "buy" and t.price > 0:
            name = portfolio.instrument(t.symbol).name or t.name or ""
            if name and name != t.symbol:
                hints.setdefault(t.symbol, (name, []))[1].append((t.date, t.price, t.currency))
    return YahooProvider().load(symbols, tx_currency, portfolio.base_currency, start, hints)


def demo_portfolio() -> Portfolio:
    content = resources.files("atlas").joinpath("data/demo_portfolio.csv").read_bytes()
    imported = parse_file(content)
    return Portfolio(name="Portefeuille de démonstration", transactions=imported.transactions,
                     instruments=imported.instruments)


class ComputeRequest(BaseModel):
    transactions: list[Transaction]
    instruments: dict[str, Instrument] = Field(default_factory=dict)
    base_currency: str = "EUR"
    params: dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


# Titres publics de référence pour vérifier que le fournisseur répond (aucune donnée d'utilisateur)
MARKET_CHECK = {"US0378331005": "EUR", "IE000BI8OT95": "EUR", "FR0000121014": "EUR", "XF000BTC0017": "EUR"}


@app.get("/market/check")
def market_check(symbols: str | None = None, name: str | None = None, on: str | None = None,
                 price: float | None = None) -> dict[str, Any]:
    """Diagnostic : le fournisseur de cours configuré résout-il ces titres (ISIN séparés par des virgules,
    40 au plus ; à défaut, quelques titres publics de référence) ? `name`, `on` et `price` décrivent un achat
    du premier titre, pour éprouver le repli par le nom."""
    wanted = {s.strip().upper(): "EUR" for s in (symbols or "").split(",") if s.strip()}
    if len(wanted) > 40:
        raise HTTPException(422, "40 titres au plus")
    check = wanted or MARKET_CHECK
    first = next(iter(check))
    pf = Portfolio(
        transactions=[Transaction(date=on if (s == first and on) else "2026-01-02", type="buy", symbol=s, quantity=1,
                                  price=price if (s == first and price) else 1, currency=c) for s, c in check.items()],
        instruments={first: Instrument(symbol=first, name=name)} if name else {},
    )
    md = load_market(pf)
    return {
        "provider": _provider_name(),
        "source": md.source,
        "as_of": md.as_of.isoformat() if md.as_of else None,
        "lines": {s: {"listing": md.listings.get(s), "currency": md.currencies.get(s),
                      "last": round(md.last_price(s)[0], 4) if md.has(s) else None,
                      "points": len(md.closes[s]) if md.has(s) else 0} for s in check},
        "fx": {c: round(float(v.iloc[-1]), 5) for c, v in md.fx.items() if not v.empty},
        "diagnostics": md.diagnostics[:40],
    }


@app.get("/modules")
def list_modules() -> list[dict[str, Any]]:
    return [{**spec.manifest, "texts": spec.texts} for spec in registry().values()]


async def _read_upload(file: UploadFile) -> bytes:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Fichier trop volumineux (5 Mo maximum)")
    if not content.strip():
        raise HTTPException(400, "Le fichier est vide")
    return content


@app.post("/imports/analyze", response_model=Analysis)
async def analyze_import(file: UploadFile = File(...)) -> Analysis:
    """Devine le format et la correspondance des colonnes, sans rien importer."""
    content = await _read_upload(file)
    try:
        return analyze_file(content, file.filename or "")
    except ValueError as exc:  # PDF scanné ou sans opération reconnue : message déjà rédigé
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # fichier corrompu, Excel protégé…
        raise HTTPException(400, f"Fichier illisible : {exc}") from exc


@app.post("/imports", response_model=ImportResult)
async def import_file(file: UploadFile = File(...), mapping: str | None = Form(None),
                      extras: str | None = Form(None)) -> ImportResult:
    """Convertit le fichier en transactions. `mapping` (JSON champ -> index de colonne) est optionnel."""
    content = await _read_upload(file)
    try:
        parsed_mapping = {k: int(v) for k, v in json.loads(mapping).items()} if mapping else None
        parsed_extras = {k: int(v) for k, v in json.loads(extras).items()} if extras else None
    except (ValueError, AttributeError) as exc:
        raise HTTPException(422, "Correspondance de colonnes invalide") from exc
    try:
        return parse_file(content, file.filename or "", parsed_mapping, parsed_extras)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Fichier illisible : {exc}") from exc


def _run(module_id: str, portfolio: Portfolio, params: dict[str, Any], demo: bool = False) -> ModuleResult:
    if module_id not in registry():
        raise HTTPException(404, f"Module inconnu : {module_id}")
    try:
        return run(module_id, portfolio, load_market(portfolio, demo=demo), params)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/compute/{module_id}", response_model=ModuleResult)
def compute(module_id: str, req: ComputeRequest) -> ModuleResult:
    portfolio = Portfolio(transactions=req.transactions, instruments=req.instruments, base_currency=req.base_currency)
    return _run(module_id, portfolio, req.params)


@app.get("/demo/{module_id}", response_model=ModuleResult)
def demo(module_id: str) -> ModuleResult:
    return _run(module_id, demo_portfolio(), {}, demo=True)
