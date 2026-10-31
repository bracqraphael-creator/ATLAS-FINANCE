"""API HTTP du moteur de calcul."""

from __future__ import annotations

import json
import os
from importlib import resources
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import __version__
from .core.importers import Analysis, ImportResult, analyze_file, parse_file
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
