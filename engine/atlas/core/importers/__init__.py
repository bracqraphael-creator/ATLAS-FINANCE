"""Imports de portefeuilles.

`analyze_file` devine le format et la correspondance des colonnes ; `parse_file` convertit le fichier
(avec la correspondance devinée, ou celle corrigée par l'utilisateur).
Préréglages courtiers : voir `universal.py` (DEGIRO pour l'instant ; d'autres s'ajoutent à partir de vrais fichiers).
"""

from __future__ import annotations

from .reader import Sheet, read_table
from .standard_csv import parse_standard_csv
from .universal import Analysis, ImportResult, RejectedRow, analyze, convert


def analyze_file(content: bytes | str, filename: str = "") -> Analysis:
    return analyze(read_table(content, filename))


def parse_file(content: bytes | str, filename: str = "", mapping: dict[str, int] | None = None,
               extras: dict[str, int] | None = None) -> ImportResult:
    sheet = read_table(content, filename)
    detected = analyze(sheet)
    if mapping is None:
        return convert(sheet, detected.mapping, detected.extras, detected.format, detected.format_label)
    return convert(sheet, mapping, extras or {}, "custom", "Correspondance personnalisée")


__all__ = ["Analysis", "ImportResult", "RejectedRow", "Sheet", "analyze_file", "parse_file", "parse_standard_csv"]
