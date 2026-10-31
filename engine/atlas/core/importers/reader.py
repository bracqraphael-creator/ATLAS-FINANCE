"""Lecture brute d'un fichier d'export : CSV (tout séparateur, tout encodage courant) ou Excel.

Renvoie un tableau : une liste d'en-têtes et une liste de lignes (listes de cellules texte ou valeurs).
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")
XLSX_MAGIC = b"PK\x03\x04"


class Sheet(BaseModel):
    headers: list[str]
    rows: list[list[Any]]
    source: str = "csv"  # csv | xlsx


def _decode(content: bytes) -> str:
    for enc in ENCODINGS:
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _sniff(text: str) -> str:
    sample = "\n".join(text.splitlines()[:20])
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
    except csv.Error:
        first = text.splitlines()[0] if text else ""
        return max(";,\t|", key=first.count)


def _header_index(rows: list[list[Any]]) -> int:
    """Certains exports commencent par des lignes de titre : l'en-tête est la première ligne
    « large » (au moins 3 cellules remplies) parmi les 15 premières."""
    for i, row in enumerate(rows[:15]):
        if sum(1 for c in row if str(c).strip()) >= 3:
            return i
    return 0


def _finish(rows: list[list[Any]], source: str) -> Sheet:
    rows = [r for r in rows if any(str(c).strip() for c in r if c is not None)]
    if not rows:
        return Sheet(headers=[], rows=[], source=source)
    h = _header_index(rows)
    headers = [str(c).strip() if c is not None else "" for c in rows[h]]
    width = len(headers)
    body = [(list(r) + [""] * width)[:width] for r in rows[h + 1:]]
    return Sheet(headers=headers, rows=body, source=source)


def read_table(content: bytes | str, filename: str = "") -> Sheet:
    if isinstance(content, bytes) and content[:4] == b"%PDF":
        from .pdf import read_pdf  # import local : évite une dépendance circulaire
        return read_pdf(content)
    if isinstance(content, bytes) and (content[:4] == XLSX_MAGIC or filename.lower().endswith((".xlsx", ".xlsm"))):
        return _read_xlsx(content)
    text = content if isinstance(content, str) else _decode(content)
    text = text.lstrip("﻿")
    if not text.strip():
        return Sheet(headers=[], rows=[])
    reader = csv.reader(io.StringIO(text), delimiter=_sniff(text))
    return _finish([list(r) for r in reader], "csv")


def _read_xlsx(content: bytes) -> Sheet:
    from openpyxl import load_workbook  # import local : dépendance chargée seulement si besoin

    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows: list[list[Any]] = []
    for row in ws.iter_rows(values_only=True):
        rows.append([
            c.date().isoformat() if isinstance(c, datetime) else c.isoformat() if isinstance(c, date)
            else "" if c is None else c
            for c in row
        ])
    wb.close()
    return _finish(rows, "xlsx")
