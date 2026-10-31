"""Import du format CSV standard d'ATLAS.

Colonnes : date, type, symbol, name, quantity, price, currency, fees, amount, asset_class, country, sector
(seules date et type sont toujours obligatoires). Séparateur « , » ou « ; », décimales « . » ou « , »,
dates AAAA-MM-JJ ou JJ/MM/AAAA, types en anglais ou en français.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime

from pydantic import BaseModel, Field, ValidationError

from ..models import AssetClass, Instrument, Transaction, TransactionType

TYPE_ALIASES = {
    "buy": "buy", "achat": "buy",
    "sell": "sell", "vente": "sell",
    "dividend": "dividend", "dividende": "dividend",
    "fee": "fee", "frais": "fee",
    "deposit": "deposit", "depot": "deposit", "dépôt": "deposit", "versement": "deposit",
    "withdrawal": "withdrawal", "retrait": "withdrawal",
    "split": "split", "division": "split",
}

CLASS_ALIASES = {
    "action": "equity", "actions": "equity", "equity": "equity", "stock": "equity",
    "etf": "etf", "tracker": "etf",
    "obligation": "bond", "bond": "bond",
    "crypto": "crypto", "cryptomonnaie": "crypto",
    "cash": "cash", "liquidités": "cash", "liquidites": "cash",
    "fonds": "fund", "fund": "fund", "opcvm": "fund", "scpi": "fund",
    "matière première": "commodity", "matiere premiere": "commodity", "commodity": "commodity", "or": "commodity",
}

REQUIRED = {"date", "type"}


class RejectedRow(BaseModel):
    line: int
    reason: str


class ImportResult(BaseModel):
    format: str = "atlas-standard"
    transactions: list[Transaction] = Field(default_factory=list)
    instruments: dict[str, Instrument] = Field(default_factory=dict)
    rejected: list[RejectedRow] = Field(default_factory=list)


def _number(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = raw.strip().replace(" ", "").replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:          # 1.234,56 ou 1,234.56
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    return float(s)


def _date(raw: str) -> date:
    s = raw.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"date illisible « {raw} »")


def _sniff_delimiter(text: str) -> str:
    first = text.splitlines()[0] if text else ""
    return ";" if first.count(";") > first.count(",") else ","


def parse_standard_csv(content: str | bytes) -> ImportResult:
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else content.lstrip("﻿")
    result = ImportResult()
    if not text.strip():
        return result

    reader = csv.DictReader(io.StringIO(text), delimiter=_sniff_delimiter(text))
    headers = {h.strip().lower() for h in (reader.fieldnames or [])}
    missing = REQUIRED - headers
    if missing:
        result.rejected.append(RejectedRow(line=1, reason=f"colonnes manquantes : {', '.join(sorted(missing))}"))
        return result

    for line_no, raw in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        if not any(row.values()):
            continue
        try:
            ttype = TYPE_ALIASES.get(row["type"].lower())
            if not ttype:
                raise ValueError(f"type inconnu « {row['type']} »")
            tx = Transaction(
                date=_date(row["date"]),
                type=TransactionType(ttype),
                symbol=row.get("symbol") or None,
                name=row.get("name") or None,
                quantity=_number(row.get("quantity")) or 0.0,
                price=_number(row.get("price")) or 0.0,
                currency=row.get("currency") or "EUR",
                fees=_number(row.get("fees")) or 0.0,
                amount=_number(row.get("amount")),
            )
            if tx.type in (TransactionType.BUY, TransactionType.SELL):
                if not tx.symbol:
                    raise ValueError("symbole obligatoire pour un achat ou une vente")
                if tx.quantity <= 0 or tx.price <= 0:
                    raise ValueError("quantité et prix doivent être positifs")
            if tx.type in (TransactionType.DIVIDEND, TransactionType.FEE, TransactionType.DEPOSIT,
                           TransactionType.WITHDRAWAL) and tx.amount is None:
                raise ValueError("montant (amount) obligatoire pour ce type d'opération")
        except (ValueError, ValidationError) as exc:
            msg = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
            result.rejected.append(RejectedRow(line=line_no, reason=msg))
            continue

        result.transactions.append(tx)
        if tx.symbol and tx.symbol not in result.instruments:
            cls = CLASS_ALIASES.get((row.get("asset_class") or "").lower(), "other")
            result.instruments[tx.symbol] = Instrument(
                symbol=tx.symbol,
                name=tx.name,
                asset_class=AssetClass(cls),
                currency=tx.currency,
                country=row.get("country") or None,
                sector=row.get("sector") or None,
            )
    return result
