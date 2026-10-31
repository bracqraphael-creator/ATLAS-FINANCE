"""Registre des modules : découvre chaque dossier de `atlas/modules/` contenant un manifest.json."""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .market import MarketData
from .models import Portfolio
from .result import ModuleResult

MODULES_DIR = Path(__file__).resolve().parent.parent / "modules"
PLAN_ORDER = ["free", "base", "pro", "trader", "advisor"]

ComputeFn = Callable[[Portfolio, MarketData, dict[str, Any]], ModuleResult]


@dataclass
class ModuleSpec:
    id: str
    manifest: dict[str, Any]
    texts: dict[str, Any]
    compute: ComputeFn

    def defaults(self) -> dict[str, Any]:
        return {p["key"]: p["default"] for p in self.manifest.get("params", [])}

    def resolve_params(self, given: dict[str, Any] | None) -> dict[str, Any]:
        """Réglages validés selon leur type : « number » (bornes), « symbols » (liste de codes, texte séparé par
        des virgules accepté), « allocation » (code -> poids en %, positifs)."""
        params = self.defaults()
        for p in self.manifest.get("params", []):
            key, kind = p["key"], p.get("type", "number")
            if not given or key not in given or given[key] is None:
                continue
            value = given[key]
            if kind == "symbols":
                items = value.split(",") if isinstance(value, str) else value
                if not isinstance(items, list):
                    raise ValueError(f"Paramètre {key} : liste de codes attendue")
                codes = [str(x).strip().upper() for x in items if str(x).strip()]
                if len(codes) > p.get("max_items", 8):
                    raise ValueError(f"Paramètre {key} : {p.get('max_items', 8)} titres au plus")
                params[key] = codes
            elif kind == "allocation":
                if not isinstance(value, dict) or not all(isinstance(v, (int, float)) and v >= 0 for v in value.values()):
                    raise ValueError(f"Paramètre {key} : répartition (poids positifs) attendue")
                params[key] = {str(k): float(v) for k, v in value.items() if v > 0}
            else:
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise ValueError(f"Paramètre {key} : nombre attendu")
                if "min" in p and value < p["min"] or "max" in p and value > p["max"]:
                    raise ValueError(f"Paramètre {key} hors bornes [{p.get('min')}, {p.get('max')}]")
                params[key] = value
        return params

    def allowed_for(self, plan: str) -> bool:
        need = self.manifest.get("plan", "free")
        return PLAN_ORDER.index(plan) >= PLAN_ORDER.index(need)


def discover(modules_dir: Path = MODULES_DIR) -> dict[str, ModuleSpec]:
    specs: dict[str, ModuleSpec] = {}
    for folder in sorted(p for p in modules_dir.iterdir() if (p / "manifest.json").is_file()):
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        texts_file = folder / "texts.fr.json"
        texts = json.loads(texts_file.read_text(encoding="utf-8")) if texts_file.is_file() else {}
        mod = importlib.import_module(f"atlas.modules.{folder.name}.compute")
        if manifest["id"] != folder.name:
            raise ValueError(f"L'id du manifest ({manifest['id']}) doit égaler le nom du dossier ({folder.name})")
        specs[manifest["id"]] = ModuleSpec(manifest["id"], manifest, texts, mod.compute)
    return dict(sorted(specs.items(), key=lambda kv: kv[1].manifest.get("order", 1000)))


_REGISTRY: dict[str, ModuleSpec] | None = None


def registry() -> dict[str, ModuleSpec]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = discover()
    return _REGISTRY


def run(module_id: str, portfolio: Portfolio, market: MarketData, params: dict[str, Any] | None = None) -> ModuleResult:
    spec = registry().get(module_id)
    if spec is None:
        raise KeyError(f"Module inconnu : {module_id}")
    result = spec.compute(portfolio, market, spec.resolve_params(params))
    if not result.method:
        result.method = spec.texts.get("method", "")
    return result
