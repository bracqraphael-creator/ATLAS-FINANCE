"""Relevé de compte Trade Republic (PDF « Relevé de compte » généré depuis l'application).

Mise en page : un tableau DATE | TYPE | DESCRIPTION | ENTRÉE D'ARGENT | SORTIE D'ARGENT | SOLDE, une section
par compte (compte courant, PEA…), chacune précédée d'une synthèse (solde début, entrées, sorties, solde fin).

- La date est éclatée sur plusieurs lignes (« 09 oct. » / « 2024 », parfois « 17 » / « août » / « 2026 ») :
  chaque opération est reconstruite à partir de la position des mots, pas du texte à plat.
- Le sens (entrée ou sortie) vient de la colonne du montant ; il est recoupé avec le solde courant.
- Les quantités sont au format anglais (« quantity: 0.617977 ») : le point est un séparateur décimal.
- Le relevé ne donne pas le cours : prix unitaire = montant / quantité (frais de 1 € inclus pour les ordres).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

from .reader import Sheet

HEADERS = ["Date", "Type", "ISIN", "Nom", "Quantité", "Cours", "Devise", "Frais", "Montant", "Classe", "Compte"]

MONTHS = {
    "janv": 1, "jan": 1, "janvier": 1, "fevr": 2, "fev": 2, "feb": 2, "fevrier": 2, "mars": 3, "mar": 3, "marz": 3,
    "avr": 4, "apr": 4, "avril": 4, "mai": 5, "may": 5, "juin": 6, "jun": 6, "juil": 7, "jul": 7, "juillet": 7,
    "aout": 8, "aug": 8, "sept": 9, "sep": 9, "oct": 10, "okt": 10, "nov": 11, "dec": 12, "dez": 12,
}
ISIN_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b")
AMOUNT_RE = re.compile(r"^-?\d[\d.  ]*,\d{2}\s?€?$")   # « 50,00 » ou « 50,00€ » (mot collé au symbole)
QTY_RE = re.compile(r"(?:quantity|quantit[ée]|menge|st[üu]ck)\s*:?\s*([\d.,]+)", re.IGNORECASE)
TRADE_WORDS = re.compile(r"\b(buy|sell|trade|savings plan|achat|vente|ordre|kauf|verkauf|sparplan)\b", re.IGNORECASE)
INCOME_WORDS = re.compile(r"(dividend|interest\s?payment|distribution|coupon|ausschüttung|zinszahlung)", re.IGNORECASE)
CRYPTO_NAMES = {"BTC": "Bitcoin", "ETH": "Ethereum", "TRX": "Tron", "AVAX": "Avalanche", "LINK": "Chainlink",
                "ADA": "Cardano", "MATIC": "Polygon", "XRP": "XRP", "SOL": "Solana", "DOGE": "Dogecoin",
                "DOT": "Polkadot", "LTC": "Litecoin", "BCH": "Bitcoin Cash", "XLM": "Stellar", "UNI": "Uniswap"}
TAX_WORDS = re.compile(r"\b(tax|taxe|imp[ôo]t|steuer|prélèvement)", re.IGNORECASE)


def is_trade_republic(first_page_text: str) -> bool:
    t = first_page_text.upper()
    return "TRADE REPUBLIC" in t and "TRANSACTIONS" in t and "SOLDE" in t


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip(".")


def _amount(text: str) -> float:
    text = text.replace("€", "").strip()
    return float(text.replace(".", "").replace(" ", "").replace(" ", "").replace(",", "."))


def _qty(text: str) -> float:
    text = text.rstrip(".,")
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    return float(text.replace(",", ""))


def _lines(words: list[dict]) -> list[list[dict]]:
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(lines[-1][0]["top"] - w["top"]) < 2.5:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _text(words: list[dict]) -> str:
    return " ".join(" ".join(w["text"] for w in line) for line in _lines(words)).strip()


class _Account:
    def __init__(self, name: str, start: float | None, end: float | None):
        self.name, self.start, self.end = name, start, end
        self.balance = start
        self.count = 0
        self.mismatches = 0


def read_trade_republic(pages: list[Any]) -> Sheet:
    rows: list[list[str]] = []
    accounts: list[_Account] = []
    descs: list[str] = []
    account: _Account | None = None

    for page in pages:
        words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
        lines = _lines(words)

        # Synthèse : « PRODUIT | SOLDE DÉBUT | ENTRÉE | SORTIE | SOLDE FIN » puis « Compte courant 0,00 € … »
        for i, line in enumerate(lines):
            if line[0]["text"] == "PRODUIT" and i + 1 < len(lines):
                nxt = lines[i + 1]
                first_amount = next((k for k, w in enumerate(nxt) if AMOUNT_RE.match(w["text"])), len(nxt))
                amounts = [_amount(w["text"]) for w in nxt if AMOUNT_RE.match(w["text"])]
                name = " ".join(w["text"] for w in nxt[:first_amount]) or f"Compte {len(accounts) + 1}"
                account = _Account(name, amounts[0] if amounts else None, amounts[-1] if len(amounts) >= 4 else None)
                accounts.append(account)

        header = next((ln for ln in lines if ln[0]["text"] == "DATE" and any(w["text"] == "DESCRIPTION" for w in ln)), None)
        if header is None:
            continue
        if account is None:
            account = _Account("Compte", None, None)
            accounts.append(account)
        type_x = next(w["x0"] for w in header if w["text"] == "TYPE")
        desc_x = next(w["x0"] for w in header if w["text"] == "DESCRIPTION")
        solde = next(w for w in header if w["text"] == "SOLDE")
        top0 = max(w["bottom"] for w in words if abs(w["top"] - header[0]["top"]) < 8)
        # Seuil entrée / sortie : lettres verticales de l'en-tête (« E » d'ENTRÉE, « S » de SORTIE)
        band = [w for w in words if abs(w["top"] - header[0]["top"]) < 8 and desc_x + 150 < w["x0"] < solde["x0"]]
        e_x = next((w["x0"] for w in band if w["text"].startswith("E")), solde["x0"] - 74)
        s_x = next((w["x0"] for w in band if w["text"].startswith("S")), solde["x0"] - 43)
        split_x = (e_x + s_x) / 2

        # Fin du tableau : pied de page ou section suivante (APERÇU DU SOLDE, REMARQUES…)
        end = page.height
        for w in words:
            if w["top"] > top0 and (w["text"] in ("www.traderepublic.fr",) or
                                    (w["x0"] < type_x and w["text"].isupper() and len(w["text"]) > 3)):
                end = min(end, w["top"] - 1)
        body = [w for w in words if top0 < w["top"] < end]
        days = sorted((w for w in body if w["x0"] < type_x - 2 and re.fullmatch(r"\d{1,2}", w["text"])),
                      key=lambda w: w["top"])
        for k, day in enumerate(days):
            lo = day["top"] - 3
            hi = days[k + 1]["top"] - 3 if k + 1 < len(days) else end
            block = [w for w in body if lo <= w["top"] < hi]
            parsed = _parse_block(block, type_x, desc_x, split_x, account)
            if parsed is None:
                continue
            rows.append(parsed[0])
            descs.append(parsed[1])

    # Noms manquants (achats directs de crypto, dividendes « for ISIN … ») : repris des autres lignes du même titre
    names = {r[2]: r[3] for r in rows if r[2] and r[3]}
    for r in rows:
        if r[2] and not r[3]:
            ticker = re.match(r"XF000([A-Z]+)", r[2])
            r[3] = names.get(r[2]) or (CRYPTO_NAMES.get(ticker.group(1), ticker.group(1)) if ticker else r[2])
        if r[2] and r[1] in ("dividend",) and r[3] == r[2]:
            r[3] = f"Revenu {r[2]}"

    fee_count = _order_fees(rows, descs)
    synthetic = _amount_only_trades(rows, descs)
    _classify(rows, descs)
    no_qty = [f"{r[0]} {r[3]}" for r in rows if r[4] == "" and r[1] in ("buy", "sell")]

    notes = [f"Relevé de compte Trade Republic : {sum(a.count for a in accounts)} opérations lues."]
    for a in accounts:
        if a.count == 0:
            continue
        line = f"{a.name} : {a.count} opérations"
        if a.end is not None and a.balance is not None:
            ok = abs(a.balance - a.end) < 0.015
            line += (f", solde final recalculé {_fr(a.balance)} € = solde du relevé" if ok
                     else f", solde final recalculé {_fr(a.balance)} € ≠ {_fr(a.end)} € indiqué : vérifiez l'aperçu")
        notes.append(line + ".")
    if len([a for a in accounts if a.count]) > 1:
        notes.append("Les virements entre comptes (« Versement PEA ») figurent comme retrait d'un côté et "
                     "versement de l'autre.")
    notes.append("Le relevé ne donne pas le cours d'exécution : prix unitaire = (montant ∓ frais) / quantité.")
    if fee_count:
        notes.append(f"{fee_count} ordre(s) ponctuel(s) : frais de 1 € par ordre (tarif Trade Republic) séparés du "
                     "prix. Les plans d'épargne et la partie fractionnaire d'un ordre partagé sont sans frais.")
    if synthetic:
        notes.append(f"{synthetic} opération(s) sans quantité dans le relevé (achats directs de crypto, Private "
                     "Markets) importées en montants : 1 part = 1 € investi, valorisée au prix d'achat. Une vente "
                     "sans quantité solde la ligne ; la plus ou moins-value réalisée est donc exacte.")
    if no_qty:
        notes.append(f"{len(no_qty)} achat(s)/vente(s) sans quantité n'ont pas pu être rapprochés et ne sont pas "
                     "importés. Ajoutez-les à la main ou utilisez l'export CSV de l'application.")
    return Sheet(headers=HEADERS, rows=rows, source="pdf-traderepublic", notes=notes)


ORDER_FEE = 1.0


def _is_integer(q: float) -> bool:
    return abs(q - round(q)) < 1e-9


def _order_fees(rows: list[list[str]], descs: list[str]) -> int:
    """Sépare les frais de 1 € des ordres ponctuels (« Buy trade » / « Sell trade ») et calcule le cours.

    Trade Republic facture 1 € par ordre ; les plans d'épargne sont gratuits. Un ordre portant sur des titres
    entiers et une fraction est éclaté en deux lignes le même jour (« quantity: 5 » puis « quantity: 0.617977 ») :
    les frais ne figurent que sur la ligne des titres entiers. Vérifié sur un vrai relevé : 5,45 € pour 5 titres et
    0,55 € pour 0,617977 donnent le même cours, 0,89 €, une fois 1 € retiré de la première ligne."""
    count = 0
    for i, (r, desc) in enumerate(zip(rows, descs)):
        if r[1] not in ("buy", "sell"):
            continue
        amount = float(r[8])
        if not r[4]:
            continue
        qty = float(r[4])
        fee = 0.0
        if re.search(r"\b(buy|sell)\s+trade\b", desc, re.IGNORECASE):
            whole_sibling = any(o is not r and o[0] == r[0] and o[1] == r[1] and o[2] == r[2] and o[4]
                                and _is_integer(float(o[4])) for o in rows)
            if _is_integer(qty) or not whole_sibling:
                fee = ORDER_FEE
        if r[1] == "buy" and amount - fee <= 0:
            fee = 0.0
        gross = amount - fee if r[1] == "buy" else amount + fee
        r[5] = repr(gross / qty)
        r[7] = f"{fee:g}" if fee else ""
        count += fee > 0
    return count


def _amount_only_trades(rows: list[list[str]], descs: list[str]) -> int:
    """Achats directs de crypto et Private Markets : le relevé ne donne que le montant. Ils sont importés en
    « parts d'un euro » sur une ligne distincte (jamais mêlée aux achats de la même crypto avec quantité, ni
    rattachée à un cours de marché) : achat de 41,44 € = 41,44 parts à 1 €. Une vente sans quantité solde toutes
    les parts ouvertes à son montant, ce qui donne la plus ou moins-value réalisée exacte. Une vente qui ne suit
    aucun achat sans quantité reste non importée."""
    held: dict[tuple[str, str], float] = {}
    count = 0
    for r, desc in zip(rows, descs):
        if r[1] not in ("buy", "sell") or r[4]:
            continue
        amount = float(r[8])
        if r[2].startswith("XF000"):
            ticker = re.match(r"XF000([A-Z]+)", r[2]).group(1)
            symbol, label = f"{ticker}-EUR-TR", f"{r[3]} (achat direct, montants en €)"
        elif re.search(r"private\s+markets", f"{r[3]} {desc}", re.IGNORECASE):
            symbol, label = "PRIVATE-MARKETS-TR", "Private Markets (montants en €)"
        else:
            continue
        key = (r[10], symbol)
        if r[1] == "buy":
            held[key] = held.get(key, 0.0) + amount
            qty = amount
        else:
            qty = held.pop(key, 0.0)
            if qty <= 0:
                continue
        r[2], r[3], r[4], r[5] = symbol, label, repr(qty), repr(amount / qty)
        count += 1
    return count


def _classify(rows: list[list[str]], descs: list[str]) -> None:
    """Classe d'actif : utile au module d'exposition (actions, ETF, obligations, crypto, matières premières).
    Une ligne qui verse des intérêts (« Interest Payment for ISIN … ») est une obligation."""
    bonds = {r[2] for r, d in zip(rows, descs) if r[1] == "dividend" and r[2] and re.search(r"interest", d, re.I)}
    for r in rows:
        if not r[2]:
            continue
        name = r[3]
        if r[2] in bonds or re.search(r"\b\d{2}/\d{2}\b", name):
            r[9] = "bond"
        elif r[2].startswith("XF000") or r[2].endswith("-EUR-TR"):
            r[9] = "crypto"
        elif r[2] == "PRIVATE-MARKETS-TR":
            r[9] = "fund"
        elif re.search(r"\b(physical|gold|xau|silver|etc)\b", name, re.IGNORECASE):
            r[9] = "commodity"
        elif re.search(r"\b(ETF|UCITS)\b", name):
            r[9] = "etf"
        elif ISIN_RE.fullmatch(r[2]):
            r[9] = "equity"


def _fr(v: float) -> str:
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


def _parse_block(block: list[dict], type_x: float, desc_x: float, split_x: float,
                 acc: _Account) -> tuple[list[str], str] | None:
    amounts = [w for w in block if w["x0"] > split_x - 40 and AMOUNT_RE.match(w["text"])]
    if len(amounts) < 2:
        return None
    amounts.sort(key=lambda w: w["x0"])
    move, bal = amounts[0], amounts[-1]
    value = _amount(move["text"])
    balance = _amount(bal["text"])
    inflow = move["x0"] < split_x
    # Recoupement avec le solde courant : il tranche si la colonne est ambiguë
    if acc.balance is not None:
        if abs(acc.balance + (value if inflow else -value) - balance) > 0.015:
            if abs(acc.balance + (-value if inflow else value) - balance) < 0.015:
                inflow = not inflow
            else:
                acc.mismatches += 1
    acc.balance = balance
    acc.count += 1

    date_words = [w for w in block if w["x0"] < type_x - 2]
    type_words = [w for w in block if type_x - 2 <= w["x0"] < desc_x - 2]
    desc_words = [w for w in block if desc_x - 2 <= w["x0"] and w not in amounts and w["text"] not in ("€",)
                  and w["x0"] < split_x - 40]
    d = _date(date_words)
    kind = _text(type_words)
    desc = _text(desc_words)
    full = f"{kind} {desc}"
    # « Rendement » déborde sur la colonne DESCRIPTION (« RendementCash Dividend… ») : mots-clés cherchés sans espaces
    compact = re.sub(r"\s+", "", full)

    isin_m = ISIN_RE.search(desc)
    isin = isin_m.group(1) if isin_m else ""
    qty_m = QTY_RE.search(desc)
    qty = _qty(qty_m.group(1)) if qty_m else None
    name = ""
    if isin:
        name = desc[isin_m.end():qty_m.start() if qty_m and qty_m.start() > isin_m.end() else len(desc)]
        name = re.sub(r"\s+", " ", name).strip(" ,")
        if re.fullmatch(r"[A-Z]?\s?\d{6,}", name):   # numéro d'ordre (achats directs de crypto)
            name = ""

    is_trade = qty is not None or ("xécution" in kind or "xecution" in kind.lower()) and TRADE_WORDS.search(full)
    if is_trade and not INCOME_WORDS.search(desc):
        ttype = "sell" if inflow else "buy"
        if not name:
            name = "" if isin else re.sub(r"\b(Buy|Sell) trade|Exécution|Savings plan execution|Achat direct|"
                                          r"Vente directe|Ordre d'(?:achat|vente)", "", desc).strip(" ,")
    elif INCOME_WORDS.search(compact):
        ttype = "dividend" if inflow else "fee"
        name = ""   # complété plus bas avec le nom du titre lu dans les achats
    elif TAX_WORDS.search(full):
        ttype = "fee" if not inflow else "deposit"
        name = desc
    else:
        ttype = "deposit" if inflow else "withdrawal"
        isin, name = "", _cash_label(desc, inflow)

    return [d.isoformat() if d else "", ttype, isin, name, f"{qty:.10g}" if qty else "", "", "EUR", "",
            f"{value:.2f}", "", acc.name], full


def _cash_label(desc: str, inflow: bool) -> str:
    """Libellés lisibles pour les mouvements d'espèces (le relevé mêle anglais, français et IBAN complets)."""
    d = desc.lower()
    if "versement pea" in d:
        return "Versement PEA"
    if "activation" in d:
        return "Activation PEA"
    if "apple pay" in d or "google pay" in d or "top up" in d:
        return "Dépôt par carte"
    if "payout" in d:
        return "Retrait"
    if any(k in d for k in ("transfer", "paiement accepté", "virement", "sepa")):
        return "Virement reçu" if inflow else "Virement émis"
    return desc


def _date(words: list[dict]) -> date | None:
    tokens = [_norm(w["text"]) for w in sorted(words, key=lambda w: (w["top"], w["x0"]))]
    day = next((int(t) for t in tokens if re.fullmatch(r"\d{1,2}", t)), None)
    year = next((int(t) for t in tokens if re.fullmatch(r"\d{4}", t)), None)
    month = next((MONTHS[t] for t in tokens if t in MONTHS), None)
    if day and month and year:
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


__all__ = ["is_trade_republic", "read_trade_republic"]
