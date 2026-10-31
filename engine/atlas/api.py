"""API HTTP du moteur de calcul."""

from __future__ import annotations

import os
from importlib import resources
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import __version__
from .core.importers import ImportResult, parse_file
from .core.market import MarketData
from .core.models import Instrument, Portfolio, Transaction
from .core.providers import DemoProvider, EodhdProvider
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


def load_market(portfolio: Portfolio) -> MarketData:
    symbols = sorted({t.symbol for t in portfolio.transactions if t.symbol})
    provider = os.environ.get("MARKET_DATA_PROVIDER", "demo").lower()
    if provider == "eodhd":
        currencies = {s: portfolio.instrument(s).currency for s in symbols}
        return EodhdProvider(os.environ.get("MARKET_DATA_API_KEY", "")).load(symbols, currencies, portfolio.base_currency)
    return DemoProvider().load(symbols, portfolio.base_currency)


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


@app.get("/modules")
def list_modules() -> list[dict[str, Any]]:
    return [{**spec.manifest, "texts": spec.texts} for spec in registry().values()]


@app.post("/imports", response_model=ImportResult)
async def import_file(file: UploadFile = File(...)) -> ImportResult:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Fichier trop volumineux (5 Mo maximum)")
    try:
        return parse_file(content)
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "Fichier illisible : un CSV encodé en UTF-8 est attendu") from exc


def _run(module_id: str, portfolio: Portfolio, params: dict[str, Any]) -> ModuleResult:
    if module_id not in registry():
        raise HTTPException(404, f"Module inconnu : {module_id}")
    try:
        return run(module_id, portfolio, load_market(portfolio), params)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/compute/{module_id}", response_model=ModuleResult)
def compute(module_id: str, req: ComputeRequest) -> ModuleResult:
    portfolio = Portfolio(transactions=req.transactions, instruments=req.instruments, base_currency=req.base_currency)
    return _run(module_id, portfolio, req.params)


@app.get("/demo/{module_id}", response_model=ModuleResult)
def demo(module_id: str) -> ModuleResult:
    return _run(module_id, demo_portfolio(), {})
