"""Imports de portefeuilles. Un fichier par format de courtier ; `parse_file` choisit le bon."""

from .standard_csv import ImportResult, RejectedRow, parse_standard_csv


def parse_file(content: bytes | str) -> ImportResult:
    """Détecte le format puis importe. Seul le format standard ATLAS existe pour l'instant ;
    les formats courtiers (Trade Republic, Degiro, Boursorama…) viendront s'ajouter ici."""
    return parse_standard_csv(content)


__all__ = ["ImportResult", "RejectedRow", "parse_file", "parse_standard_csv"]
