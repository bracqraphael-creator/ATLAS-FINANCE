"""Contrat de sortie commun à tous les modules.

L'interface sait afficher chaque type de bloc sans code spécifique au module.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Union

from pydantic import BaseModel, Field


def fr_number(value: float, digits: int = 2) -> str:
    """12345.678 -> « 12 345,68 » (format français, pour les textes)."""
    return f"{value:,.{digits}f}".replace(",", "\u202f").replace(".", ",")


DISCLAIMER = "Ceci n'est pas un conseil en investissement. Les performances passées ne préjugent pas des performances futures."


class Kpi(BaseModel):
    type: Literal["kpi"] = "kpi"
    id: str
    label: str
    value: float | None
    unit: str = ""          # "EUR", "%", ""
    hint: str | None = None


class Table(BaseModel):
    type: Literal["table"] = "table"
    id: str
    title: str
    columns: list[dict[str, str]]   # [{"key": "symbol", "label": "Ligne", "unit": ""}]
    rows: list[dict[str, Any]]


class TimeSeries(BaseModel):
    type: Literal["timeseries"] = "timeseries"
    id: str
    title: str
    unit: str = ""
    series: list[dict[str, Any]]    # [{"name": "Valeur", "points": [["2024-01-02", 1000.0], ...]}]


class Allocation(BaseModel):
    type: Literal["allocation"] = "allocation"
    id: str
    title: str
    slices: list[dict[str, Any]]    # [{"label": "ETF", "value": 1234.5, "weight": 0.62}]


class Bars(BaseModel):
    """Montants par période (année, mois) : histogramme vertical, valeurs négatives possibles."""
    type: Literal["bars"] = "bars"
    id: str
    title: str
    unit: str = ""
    bars: list[dict[str, Any]]      # [{"label": "2024", "value": 123.4}]


class Note(BaseModel):
    type: Literal["note"] = "note"
    id: str
    level: Literal["info", "warning"] = "info"
    text: str


Block = Union[Kpi, Table, TimeSeries, Allocation, Bars, Note]


class ModuleResult(BaseModel):
    module_id: str
    data_as_of: date | None
    blocks: list[Block] = Field(default_factory=list)
    method: str = ""
    disclaimer: str = DISCLAIMER
