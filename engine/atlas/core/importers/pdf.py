"""Lecture des PDF de courtiers : historique en tableau, avis d'opéré, relevé de portefeuille.

Le PDF est converti en un tableau aux colonnes standard (Date, Type, ISIN, Nom, Quantité, Cours, Devise,
Frais, Montant) qui suit ensuite le même chemin que les CSV : correspondance vérifiable, aperçu, import.
"""

from __future__ import annotations

import io
import re
from typing import Any

from .pdf_traderepublic import is_trade_republic, read_trade_republic
from .reader import Sheet
from .universal import parse_number, parse_type, suggest_mapping

PDF_MAGIC = b"%PDF"
HEADERS = ["Date", "Type", "ISIN", "Nom", "Quantité", "Cours", "Devise", "Frais", "Montant"]

ISIN_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b")
DATE_RE = re.compile(r"\b(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}|\d{4}-\d{2}-\d{2})\b")
# Séparateur de milliers : espace SIMPLE (le texte est extrait avec sa mise en page : plusieurs espaces
# séparent deux colonnes), espace insécable ou point.
NUMBER_RE = re.compile(r"-?\d{1,3}(?:(?:[\u00a0\u202f.]| (?! ))\d{3})+(?:,\d+)?|-?\d+(?:[.,]\d+)?")
CURRENCY_RE = re.compile(r"\b(EUR|USD|GBP|CHF|CAD|JPY|SEK|DKK|NOK)\b|€|\$|£")
OPERATION_RE = re.compile(r"\b(ACHAT|VENTE|SOUSCRIPTION|RACHAT|BUY|SELL|KAUF|VERKAUF)\b", re.IGNORECASE)


class PdfNoText(ValueError):
    """PDF sans texte (scan ou photo)."""


def is_pdf(content: bytes) -> bool:
    return content[:4] == PDF_MAGIC


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
def read_pdf(content: bytes) -> Sheet:
    import pdfplumber  # import local : dépendance chargée seulement pour les PDF

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        first = (pdf.pages[0].extract_text() or "") if pdf.pages else ""
        if is_trade_republic(first):
            sheet = read_trade_republic(pdf.pages)
            if sheet.rows:
                return sheet
        pages_text = [_page_text(p) for p in pdf.pages]
        tables: list[list[list[Any]]] = []
        for p in pdf.pages:
            tables.extend(p.extract_tables() or [])

    if not "".join(pages_text).strip():
        raise PdfNoText("Ce PDF ne contient pas de texte lisible (document scanné ou photo). "
                        "Exportez plutôt l'historique en CSV ou en PDF « texte » depuis votre courtier.")

    sheet = _from_tables(tables)
    if sheet is not None:
        return sheet
    full_text = "\n".join(pages_text)
    trades = _trade_confirmations(full_text)
    if trades:
        return Sheet(headers=HEADERS, rows=trades, source="pdf-trades")
    positions = _positions_statement(full_text)
    if positions:
        return Sheet(headers=HEADERS, rows=positions, source="pdf-positions")
    raise ValueError("Aucune opération ni position reconnue dans ce PDF. Les formats lus : historique "
                     "d'opérations en tableau, avis d'opéré, relevé de portefeuille avec codes ISIN.")


def _page_text(page: Any) -> str:
    """Texte d'une page reconstruit à partir de la position des mots : un écart nettement plus large
    qu'une espace devient « 3 espaces » (changement de colonne), un écart normal reste une espace simple.
    Cela distingue « 12   398,45 » (deux colonnes) de « 6 241,20 » (un nombre avec séparateur de milliers)."""
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not words:
        return page.extract_text() or ""
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if lines and abs(lines[-1][0]["top"] - w["top"]) < 3:
            lines[-1].append(w)
        else:
            lines.append([w])
    out = []
    for line in lines:
        line.sort(key=lambda w: w["x0"])
        char_w = sum((w["x1"] - w["x0"]) / max(len(w["text"]), 1) for w in line) / len(line)
        parts = [line[0]["text"]]
        for prev, w in zip(line, line[1:]):
            gap = w["x0"] - prev["x1"]
            parts.append(("   " if gap > 1.2 * char_w else " ") + w["text"])
        out.append("".join(parts))
    return "\n".join(out)


def _clean(cell: Any) -> str:
    return re.sub(r"\s+", " ", str(cell or "")).strip()


def _from_tables(tables: list[list[list[Any]]]) -> Sheet | None:
    """Garde le tableau (fusionné sur plusieurs pages si l'en-tête se répète) qui ressemble le plus
    à un historique d'opérations : une date et une quantité ou un montant reconnus dans l'en-tête."""
    groups: dict[tuple[str, ...], list[list[str]]] = {}
    for table in tables:
        rows = [[_clean(c) for c in r] for r in table if r and any(_clean(c) for c in r)]
        if len(rows) < 2:
            continue
        header = tuple(rows[0])
        groups.setdefault(header, []).extend(r for r in rows[1:] if tuple(r) != header)
    best: tuple[int, Sheet] | None = None
    for header, body in groups.items():
        mapping = suggest_mapping(list(header))
        if "date" not in mapping or not ({"quantity", "amount"} & set(mapping)):
            continue
        score = len(body) + 10 * len(mapping)
        if best is None or score > best[0]:
            best = (score, Sheet(headers=list(header), rows=body, source="pdf-table"))
    return best[1] if best else None


def _numbers(text: str) -> list[float]:
    stripped = ISIN_RE.sub(" ", DATE_RE.sub(" ", text))
    out = []
    for token in NUMBER_RE.findall(stripped):
        try:
            v = parse_number(token)
        except ValueError:
            continue
        if v is not None:
            out.append(v)
    return out


def _value_after(text: str, labels: list[str]) -> float | None:
    """Premier nombre qui suit l'un des libellés (sur la même ligne), ex. « Cours : 452,30 EUR »."""
    for label in labels:
        m = re.search(rf"{label}[^\n\d\-]{{0,40}}(-?\d[\d   .,]*)", text, re.IGNORECASE)
        if m:
            nums = _numbers(m.group(1))
            if nums:
                return nums[0]
    return None


def _sum_after(text: str, labels: list[str]) -> float:
    total = 0.0
    for label in labels:
        for m in re.finditer(rf"{label}[^\n\d\-]{{0,40}}(-?\d[\d   .,]*)", text, re.IGNORECASE):
            nums = _numbers(m.group(1))
            if nums:
                total += abs(nums[0])
    return total


def _last_date(text: str) -> str | None:
    """Dernière date libellée (« Date d'exécution : … ») d'un passage, sinon dernière date tout court."""
    labelled = list(re.finditer(rf"(?:ex[ée]cution|op[ée]ration|n[ée]gociation|trade date|date)[^\n\d]{{0,30}}{DATE_RE.pattern}",
                                text, re.IGNORECASE))
    if labelled:
        return labelled[-1].group(1)
    plain = DATE_RE.findall(text)
    return plain[-1] if plain else None


def _date_in(text: str) -> str | None:
    for label in ("ex[ée]cution", "date d.op[ée]ration", "date de n[ée]gociation", "trade date", "date"):
        m = re.search(rf"{label}[^\n\d]{{0,30}}{DATE_RE.pattern}", text, re.IGNORECASE)
        if m:
            return m.group(1)
    m = DATE_RE.search(text)
    return m.group(1) if m else None


def _name_near(text: str, isin: str) -> str:
    for line in text.splitlines():
        if isin in line:
            name = re.sub(r"\b(code\s+)?isin\b\s*:?", " ", line.replace(isin, " "), flags=re.IGNORECASE)
            name = re.sub(r"[:;|]+", " ", name)
            name = re.sub(r"\s+", " ", name).strip(" -")
            if len(name) >= 3 and not OPERATION_RE.fullmatch(name):
                return OPERATION_RE.sub("", name).replace("AU COMPTANT", "").strip(" -")
    return isin


def _trade_confirmations(text: str) -> list[list[str]]:
    """Avis d'opéré : un bloc par opération, commençant au mot d'opération (ACHAT, VENTE…)."""
    starts = [m.start() for m in OPERATION_RE.finditer(text)]
    rows: list[list[str]] = []
    for k, start in enumerate(starts):
        block = text[max(0, text.rfind("\n", 0, start)):starts[k + 1] if k + 1 < len(starts) else len(text)]
        isin_m = ISIN_RE.search(block)
        if not isin_m:
            continue
        qty = _value_after(block, ["quantit[ée]", "qt[ée]", "nombre de titres", "nombre", "quantity", "anzahl"])
        price = _value_after(block, ["cours", "prix unitaire", "prix", "price", "kurs"])
        if not qty or not price:
            continue
        # La date figure en général dans l'en-tête de l'avis, juste avant le mot d'opération
        preamble = text[starts[k - 1] if k else 0:start]
        date = _last_date(preamble) or _date_in(block) or ""
        fees = _sum_after(block, ["courtage", "commission", "frais", "fees", "taxe sur les transactions", "ttf"])
        net = _value_after(block, ["montant net", "net à (?:débiter|créditer)", "total net", "net amount"])
        cur = CURRENCY_RE.search(block)
        currency = {"€": "EUR", "$": "USD", "£": "GBP"}.get(cur.group(0), cur.group(0)) if cur else "EUR"
        op = parse_type(OPERATION_RE.search(block).group(0)) or ""
        rows.append([date, op, isin_m.group(1), _name_near(block, isin_m.group(1)), _fmt(qty), _fmt(price),
                     currency, _fmt(fees) if fees else "", _fmt(net) if net else ""])
    # Un même avis peut répéter le mot « ACHAT » : on dédoublonne les blocs identiques
    unique: list[list[str]] = []
    for r in rows:
        if r not in unique:
            unique.append(r)
    return unique


def _positions_statement(text: str) -> list[list[str]]:
    """Relevé de portefeuille : une ligne par titre avec ISIN, quantité, prix de revient, cours…
    Chaque position devient un achat au prix de revient à la date du relevé."""
    statement_date = None
    m = re.search(rf"\bau\s+{DATE_RE.pattern}", text, re.IGNORECASE) or DATE_RE.search(text)
    if m:
        statement_date = m.group(1)
    rows = []
    for line in text.splitlines():
        isin_m = ISIN_RE.search(line)
        if not isin_m:
            continue
        nums = [n for n in _numbers(line.split(isin_m.group(1), 1)[1])]
        if len(nums) < 2 or nums[0] <= 0 or nums[1] <= 0:
            continue
        qty, cost = nums[0], nums[1]
        cur = CURRENCY_RE.search(line)
        currency = {"€": "EUR", "$": "USD", "£": "GBP"}.get(cur.group(0), cur.group(0)) if cur else "EUR"
        name = re.sub(r"\s+", " ", line.split(isin_m.group(1), 1)[0]).strip(" -:|") or isin_m.group(1)
        rows.append([statement_date or "", "buy", isin_m.group(1), name, _fmt(qty), _fmt(cost), currency, "", ""])
    return rows


def _fmt(v: float) -> str:
    return f"{v:.10g}"


def is_positions(sheet: Sheet) -> bool:
    return sheet.source == "pdf-positions"


__all__ = ["PdfNoText", "is_pdf", "is_positions", "read_pdf"]
