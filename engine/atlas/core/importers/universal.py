"""Import universel : reconnaît les colonnes d'un export quelconque et le convertit en transactions.

1. `analyze` : devine le format (préréglage courtier ou générique) et la correspondance
   colonne -> champ ; l'utilisateur peut la corriger dans l'interface.
2. `convert` : applique une correspondance et produit les transactions + les lignes refusées.

Les correspondances utilisent l'INDEX de colonne (certains exports ont des en-têtes vides ou répétés).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ..models import AssetClass, Instrument, Transaction, TransactionType
from .reader import Sheet

# ---------------------------------------------------------------------------
# Champs reconnus
# ---------------------------------------------------------------------------
FIELDS: list[tuple[str, str]] = [
    ("date", "Date"),
    ("type", "Type d'opération"),
    ("symbol", "Symbole / ticker"),
    ("isin", "Code ISIN"),
    ("name", "Nom du titre"),
    ("quantity", "Quantité"),
    ("price", "Prix unitaire"),
    ("currency", "Devise"),
    ("fees", "Frais"),
    ("amount", "Montant"),
    ("asset_class", "Classe d'actif"),
    ("country", "Pays ou zone"),
    ("sector", "Secteur"),
    ("account", "Compte"),
]
REQUIRED = ("date",)

# Synonymes d'en-têtes (normalisés : minuscules, sans accents). FR / EN / DE / NL.
SYNONYMS: dict[str, list[str]] = {
    "date": ["date", "trade date", "date operation", "date d operation", "date execution", "date d execution",
             "transaction date", "execution date", "datum", "buchungstag", "handelstag", "timestamp", "date heure",
             "date de l operation", "date de transaction", "date valeur", "date de valeur", "settlement date"],
    "type": ["type", "operation", "type d operation", "sens", "nature", "action", "transaction type", "type operation",
             "side", "buy sell", "typ", "transaktionstyp", "soort", "mouvement", "type de mouvement", "nature operation"],
    "symbol": ["symbol", "symbole", "ticker", "mnemonique", "code valeur", "asset", "actif", "coin", "devise crypto"],
    "isin": ["isin", "code isin", "isin code", "isin nummer"],
    "name": ["name", "nom", "produit", "product", "libelle", "libelle valeur", "valeur", "instrument", "titre",
             "security", "security name", "wertpapier", "description", "designation", "nom du titre", "produkt"],
    "quantity": ["quantity", "quantite", "qte", "qty", "nombre", "nombre de titres", "nb titres", "shares", "units",
                 "anzahl", "stuck", "stuk", "aantal", "parts", "nombre de parts", "quantite executee"],
    "price": ["price", "prix", "cours", "cours d execution", "prix unitaire", "prix d execution", "kurs", "koers",
              "unit price", "price per share", "share price", "execution price", "cours execute", "spot price"],
    "currency": ["currency", "devise", "monnaie", "wahrung", "valuta", "ccy", "devise de cotation"],
    "fees": ["fees", "fee", "frais", "commission", "commissions", "courtage", "frais de courtage", "gebuhren",
             "gebuhr", "kosten", "transaction costs", "frais de transaction", "frais operation",
             "transaction and or third"],
    "amount": ["amount", "montant", "montant net", "total", "net amount", "betrag", "value", "valeur totale",
               "montant negocie", "montant total", "montant brut", "total amount", "net", "credit debit"],
    "asset_class": ["asset class", "asset_class", "classe d actif", "classe", "type d actif", "categorie"],
    "country": ["country", "pays", "zone", "zone geographique", "land"],
    "sector": ["sector", "secteur", "industrie", "branche"],
    "account": ["compte", "account", "account name", "nom du compte", "type de compte", "enveloppe", "konto",
                "depot", "portefeuille", "portfolio", "sous compte", "compte titres", "wrapper"],
}

# Mots-clés de type d'opération (contenus dans le texte de la cellule)
TYPE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("dividend", ["dividend", "dividende", "coupon", "ausschuttung", "distribution", "dividende verse"]),
    ("split", ["split", "division", "regroupement"]),
    ("withdrawal", ["withdrawal", "retrait", "auszahlung", "opname", "virement sortant", "remboursement"]),
    ("deposit", ["deposit", "depot", "versement", "einzahlung", "storting", "virement entrant", "apport"]),
    ("transfer", ["virement", "transfer", "uberweisung", "overboeking", "transfert"]),
    ("fee", ["droits de garde", "frais", "fee", "commission", "gebuhr", "kosten", "taxe", "tax"]),
    ("sell", ["sell", "vente", "verkauf", "verkoop", "sale", "cession", "vte"]),
    ("buy", ["buy", "achat", "kauf", "aankoop", "purchase", "souscription", "acquisition", "ach", "savings plan",
             "plan d investissement", "sparplan"]),
]

# Mots d'opération retirés du début d'un libellé pour retrouver le nom du titre
OPERATION_WORDS = {"achat", "vente", "comptant", "dividende", "dividendes", "coupon", "srd", "ach", "vte", "souscription",
                   "rachat", "acquisition", "cession", "buy", "sell", "dividend", "kauf", "verkauf", "de", "du", "des"}


def clean_security_name(label: str) -> str:
    words = label.split()
    while words and normalize(words[0]) in OPERATION_WORDS:
        words.pop(0)
    return " ".join(words) or label


CLASS_ALIASES = {
    "action": "equity", "actions": "equity", "equity": "equity", "stock": "equity", "share": "equity",
    "etf": "etf", "tracker": "etf", "obligation": "bond", "bond": "bond", "crypto": "crypto",
    "cryptomonnaie": "crypto", "cash": "cash", "liquidites": "cash", "fonds": "fund", "fund": "fund",
    "opcvm": "fund", "scpi": "fund", "matiere premiere": "commodity", "commodity": "commodity", "or": "commodity",
}


def normalize(text: Any) -> str:
    s = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


# ---------------------------------------------------------------------------
# Modèles d'échange avec l'interface
# ---------------------------------------------------------------------------
class RejectedRow(BaseModel):
    line: int
    reason: str


class AccountSummary(BaseModel):
    """Un compte distinct trouvé dans le fichier (PEA, compte-titres…), avec l'enveloppe devinée."""
    label: str
    wrapper: str            # pea | pea_pme | cto | assurance_vie | per | crypto | other
    count: int
    suggested_name: str


WRAPPER_LABELS = {"pea": "PEA", "pea_pme": "PEA-PME", "cto": "Compte-titres", "assurance_vie": "Assurance vie",
                  "per": "PER", "crypto": "Crypto", "other": "Autre"}


def guess_wrapper(label: str) -> str:
    """« Compte PEA » -> pea ; « Compte courant » (courtier en ligne : compte titres et espèces) -> cto…"""
    n = normalize(label)
    if re.search(r"\bpea\s*-?\s*pme\b", n):
        return "pea_pme"
    if re.search(r"\bpea\b", n):
        return "pea"
    if re.search(r"assurance\s*vie|\bav\b|life insurance", n):
        return "assurance_vie"
    if re.search(r"\bper\b|\bperp\b|perin|retraite", n):
        return "per"
    if re.search(r"crypto|bitcoin|wallet", n):
        return "crypto"
    if re.search(r"\bcto\b|titres|courant|depot|securities|brokerage|ordinaire|individual|trading|invest", n):
        return "cto"
    return "other"


class ImportResult(BaseModel):
    format: str = "generic"
    format_label: str = "Format détecté automatiquement"
    transactions: list[Transaction] = Field(default_factory=list)
    instruments: dict[str, Instrument] = Field(default_factory=dict)
    rejected: list[RejectedRow] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    accounts: list[AccountSummary] = Field(default_factory=list)   # vide si le fichier ne distingue pas de comptes


class Analysis(BaseModel):
    format: str
    format_label: str
    confidence: float                       # 0 à 1
    headers: list[str]
    mapping: dict[str, int]                 # champ -> index de colonne
    extras: dict[str, int] = Field(default_factory=dict)
    fields: list[dict[str, str]] = Field(default_factory=lambda: [{"key": k, "label": v} for k, v in FIELDS])
    missing: list[str] = Field(default_factory=list)
    sample: list[list[str]] = Field(default_factory=list)   # 5 premières lignes brutes
    row_count: int = 0


# ---------------------------------------------------------------------------
# Détection
# ---------------------------------------------------------------------------
def suggest_mapping(headers: list[str]) -> dict[str, int]:
    normalized = [normalize(h) for h in headers]
    candidates: list[tuple[int, str, int]] = []   # (score, champ, index)
    for field, syns in SYNONYMS.items():
        for i, h in enumerate(normalized):
            if not h:
                continue
            for syn in syns:
                if h == syn:
                    candidates.append((100 + len(syn), field, i))
                elif re.search(rf"(^| ){re.escape(syn)}( |$)", h):
                    candidates.append((50 + len(syn), field, i))
    mapping: dict[str, int] = {}
    used: set[int] = set()
    for _score, field, i in sorted(candidates, reverse=True):
        if field not in mapping and i not in used:
            mapping[field] = i
            used.add(i)
    # Devise souvent dans une colonne sans titre juste après le prix ou le montant
    if "currency" not in mapping:
        for anchor in ("price", "amount"):
            j = mapping.get(anchor)
            if j is not None and j + 1 < len(headers) and not normalized[j + 1] and j + 1 not in used:
                mapping["currency"] = j + 1
                break
    return mapping


def _is_degiro(norm: list[str]) -> bool:
    joined = " | ".join(norm)
    has_isin = any(h in ("code isin", "isin") for h in norm)
    has_order = any(h in ("id ordre", "order id", "order id ", "order-id", "orderid") for h in norm) or "order id" in joined
    has_venue = any(h in ("lieu d execution", "venue", "execution venue", "bourse de reference", "reference exchange",
                          "plaats van uitvoering", "ausfuhrungsort") for h in norm)
    return has_isin and has_order and has_venue


def _degiro_mapping(headers: list[str]) -> tuple[dict[str, int], dict[str, int]]:
    norm = [normalize(h) for h in headers]

    def find(*names: str) -> int | None:
        for n in names:
            if n in norm:
                return norm.index(n)
        for i, h in enumerate(norm):
            if any(h.startswith(n) for n in names):
                return i
        return None

    m: dict[str, int] = {}
    extras: dict[str, int] = {}
    for field, names in {
        "date": ("date", "datum"),
        "isin": ("code isin", "isin"),
        "name": ("produit", "product", "produkt"),
        "quantity": ("quantite", "quantity", "anzahl", "aantal"),
        "price": ("cours", "price", "kurs", "koers"),
        "fees": ("frais de courtage", "frais", "transaction and or third", "transaction costs",
                 "transaktionskosten", "transactiekosten"),
        "amount": ("montant negocie", "total", "gesamt", "totaal"),
    }.items():
        idx = find(*names)
        if idx is not None:
            m[field] = idx
    if "price" in m and m["price"] + 1 < len(headers) and not norm[m["price"] + 1]:
        m["currency"] = m["price"] + 1
    if "fees" in m and m["fees"] + 1 < len(headers) and not norm[m["fees"] + 1]:
        extras["fee_currency"] = m["fees"] + 1
    return m, extras


def analyze(sheet: Sheet) -> Analysis:
    norm = [normalize(h) for h in sheet.headers]
    sample = [[str(c) for c in r] for r in sheet.rows[:5]]
    if _is_degiro(norm):
        mapping, extras = _degiro_mapping(sheet.headers)
        fmt, label, conf = "degiro", "DEGIRO, export « Transactions »", 0.9
    else:
        mapping, extras = suggest_mapping(sheet.headers), {}
        exact = {k for k, _ in FIELDS} <= set(norm) | {"symbol", "isin", "amount", "asset_class", "country", "sector", "name"}
        if {"date", "type", "symbol", "quantity", "price"} <= set(norm):
            fmt, label = "atlas-standard", "Format standard ATLAS"
        else:
            fmt, label = "generic", "Format détecté automatiquement"
        useful = {"date", "type", "quantity", "price", "amount", "symbol", "isin", "name"}
        conf = round(min(1.0, len(useful & set(mapping)) / 6), 2)
        if exact and fmt == "atlas-standard":
            conf = 1.0
    pdf_labels = {"pdf-table": "PDF, tableau d'opérations", "pdf-trades": "PDF, avis d'opéré",
                  "pdf-positions": "PDF, relevé de portefeuille",
                  "pdf-traderepublic": "Trade Republic, relevé de compte (PDF)"}
    if sheet.source in pdf_labels:
        fmt, label = sheet.source, pdf_labels[sheet.source]
        conf = {"pdf-table": conf, "pdf-traderepublic": 0.95}.get(sheet.source, 0.9)
    missing = [f for f in REQUIRED if f not in mapping]
    if not ({"symbol", "isin", "name"} & set(mapping)):
        missing.append("symbol")
    return Analysis(format=fmt, format_label=label, confidence=conf, headers=sheet.headers, mapping=mapping,
                    extras=extras, missing=missing, sample=sample, row_count=len(sheet.rows))


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------
def parse_number(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip().replace(" ", "").replace(" ", "").replace(" ", "")
    s = re.sub(r"[€$£%]|EUR|USD|GBP|CHF", "", s, flags=re.IGNORECASE)
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    if not s or s in ("-", "--"):
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(",") == 1:
        s = s.replace(",", ".")
    elif s.count(",") > 1:
        s = s.replace(",", "")
    return float(s)


DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%y", "%d.%m.%y")


def parse_date(raw: Any) -> date:
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    s = re.split(r"[ T]", s)[0] if re.match(r"^\d{4}-\d{2}-\d{2}[ T]", s) else s.split(" ")[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"date illisible « {raw} »")


def parse_type(raw: Any) -> str | None:
    text = normalize(raw)
    if not text:
        return None
    for ttype, words in TYPE_KEYWORDS:
        if any(re.search(rf"(^| ){re.escape(w)}( |$)", text) for w in words):
            return ttype
    return None


def _cell(row: list[Any], mapping: dict[str, int], field: str) -> Any:
    i = mapping.get(field)
    if i is None or i >= len(row):
        return None
    v = row[i]
    return None if (isinstance(v, str) and not v.strip()) else v


def convert(sheet: Sheet, mapping: dict[str, int], extras: dict[str, int] | None = None,
            fmt: str = "generic", fmt_label: str = "Format détecté automatiquement") -> ImportResult:
    extras = extras or {}
    result = ImportResult(format=fmt, format_label=fmt_label)
    if "date" not in mapping:
        result.rejected.append(RejectedRow(line=1, reason="aucune colonne de date n'a été associée"))
        return result

    inferred_from_sign = 0
    name_header = normalize(sheet.headers[mapping["name"]]) if "name" in mapping and mapping["name"] < len(sheet.headers) else ""
    describes_operation = name_header in ("libelle", "libelle operation", "description", "designation", "operation detail")
    for line_no, row in enumerate(sheet.rows, start=2):
        try:
            d = parse_date(_cell(row, mapping, "date"))
            qty = parse_number(_cell(row, mapping, "quantity"))
            price = parse_number(_cell(row, mapping, "price"))
            fees = parse_number(_cell(row, mapping, "fees"))
            amount = parse_number(_cell(row, mapping, "amount"))
            currency = str(_cell(row, mapping, "currency") or "EUR").strip().upper()[:3] or "EUR"
            isin = _cell(row, mapping, "isin")
            symbol = _cell(row, mapping, "symbol") or isin or _cell(row, mapping, "name")
            symbol = str(symbol).strip() if symbol is not None else None
            name = _cell(row, mapping, "name")
            account = _cell(row, mapping, "account")
            account = re.sub(r"\s+", " ", str(account)).strip() or None if account is not None else None

            ttype = parse_type(_cell(row, mapping, "type")) if "type" in mapping else None
            if ttype is None and "type" not in mapping and describes_operation:
                # Relevés bancaires : « ACHAT COMPTANT AMUNDI… », « VENTE… » dans le libellé
                ttype = parse_type(name)
            if ttype == "transfer":
                if amount is None:
                    raise ValueError("virement sans montant")
                ttype = "deposit" if amount > 0 else "withdrawal"
            if describes_operation and name:
                name = clean_security_name(str(name))
            if ttype in ("deposit", "withdrawal", "fee") and not (_cell(row, mapping, "symbol") or isin):
                symbol = None   # mouvement d'espèces : pas de titre associé
            if ttype is None:
                if "type" in mapping and _cell(row, mapping, "type") is not None:
                    raise ValueError(f"type d'opération non reconnu « {_cell(row, mapping, 'type')} »")
                if qty:
                    ttype = "sell" if qty < 0 else "buy"
                    inferred_from_sign += 1
                elif amount is not None and (symbol is None or describes_operation) and not isin:
                    ttype = "deposit" if amount > 0 else "withdrawal"
                    symbol = None
                else:
                    raise ValueError("impossible de déterminer le type d'opération")

            qty = abs(qty) if qty is not None else 0.0
            if price is not None:
                price = abs(price)
            if (price is None or price == 0) and amount and qty:
                price = abs(amount) / qty
            fee_currency = None
            if "fee_currency" in extras:
                fc = row[extras["fee_currency"]] if extras["fee_currency"] < len(row) else ""
                fee_currency = str(fc).strip().upper()[:3] or None

            tx = Transaction(
                date=d, type=TransactionType(ttype), symbol=symbol, name=str(name).strip() if name else None,
                quantity=qty if ttype in ("buy", "sell", "split") else 0.0,
                price=price or 0.0, currency=currency,
                fees=abs(fees) if fees and (fee_currency in (None, currency)) else 0.0,
                amount=abs(amount) if amount is not None and ttype in ("dividend", "fee", "deposit", "withdrawal") else None,
                account=account,
            )
            if tx.type in (TransactionType.BUY, TransactionType.SELL):
                if not tx.symbol:
                    raise ValueError("aucun symbole, code ISIN ou nom de titre")
                if tx.quantity <= 0 or tx.price <= 0:
                    raise ValueError("quantité non indiquée dans le relevé (achat direct, Private Markets…)"
                                     if sheet.source == "pdf-traderepublic" else "quantité ou prix manquant")
            if tx.type in (TransactionType.DIVIDEND, TransactionType.FEE, TransactionType.DEPOSIT,
                           TransactionType.WITHDRAWAL) and tx.amount is None:
                raise ValueError("montant manquant pour ce type d'opération")
        except (ValueError, TypeError, ValidationError) as exc:
            msg = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
            if sheet.source == "pdf-traderepublic":   # pas de numéro de ligne parlant dans un PDF : on décrit l'opération
                msg = f"{row[0]} · {row[3]} · {row[8]} € : {msg}"
            result.rejected.append(RejectedRow(line=line_no, reason=msg))
            continue

        result.transactions.append(tx)
        # Frais facturés dans une autre devise que le titre (DEGIRO : frais en EUR sur un titre en USD) :
        # enregistrés comme frais séparés plutôt que convertis à un taux supposé.
        if fees and fee_currency and fee_currency != currency:
            result.transactions.append(Transaction(date=d, type=TransactionType.FEE, amount=abs(fees),
                                                   currency=fee_currency, symbol=None, account=account))
        if tx.symbol and tx.symbol not in result.instruments:
            cls = CLASS_ALIASES.get(normalize(_cell(row, mapping, "asset_class") or ""), "other")
            result.instruments[tx.symbol] = Instrument(
                symbol=tx.symbol, name=tx.name, asset_class=AssetClass(cls), currency=tx.currency,
                country=(str(_cell(row, mapping, "country")).strip() if _cell(row, mapping, "country") else None),
                sector=(str(_cell(row, mapping, "sector")).strip() if _cell(row, mapping, "sector") else None),
            )

    result.notes.extend(sheet.notes)
    if sheet.source == "pdf-positions":
        result.notes.append("Relevé de positions : chaque titre est enregistré comme un achat au prix de revient, "
                            "à la date du relevé. Les plus-values latentes sont justes ; l'historique antérieur n'est pas connu.")
    if sheet.source == "pdf-trades" and result.transactions:
        result.notes.append("Avis d'opéré lus dans le PDF : vérifiez les montants dans l'aperçu.")
    if inferred_from_sign and not sheet.source.startswith("pdf"):
        result.notes.append(f"{inferred_from_sign} opération(s) classées achat ou vente selon le signe de la quantité.")
    result.accounts = summarize_accounts(result.transactions, fmt, fmt_label)
    if len(result.accounts) > 1:
        result.notes.append(f"{len(result.accounts)} comptes distincts dans ce fichier : "
                            + ", ".join(f"{a.label} ({a.count} opérations, {WRAPPER_LABELS[a.wrapper]})" for a in result.accounts)
                            + ". Chacun peut être enregistré dans son propre portefeuille.")
    return result


def summarize_accounts(transactions: list[Transaction], fmt: str, fmt_label: str) -> list[AccountSummary]:
    counts: dict[str, int] = {}
    for t in transactions:
        if t.account:
            counts[t.account] = counts.get(t.account, 0) + 1
    broker = fmt_label.split(",")[0].strip() if fmt in ("pdf-traderepublic", "degiro") else ""
    out = []
    for label, n in counts.items():
        wrapper = guess_wrapper(label)
        short = WRAPPER_LABELS[wrapper] if wrapper != "other" else label
        out.append(AccountSummary(label=label, wrapper=wrapper, count=n,
                                  suggested_name=f"{broker} · {short}" if broker else label))
    return sorted(out, key=lambda a: -a.count)
