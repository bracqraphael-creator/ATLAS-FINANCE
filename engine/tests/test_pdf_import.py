"""Import de PDF : historique en tableau, avis d'opéré, relevé de portefeuille, PDF scanné."""

import io

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

from atlas.core.importers import analyze_file, parse_file


def _text_pdf(pages: list[list[str]]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for lines in pages:
        y = 800
        for line in lines:
            c.drawString(50, y, line)
            y -= 18
        c.showPage()
    c.save()
    return buf.getvalue()


def _table_pdf(rows: list[list[str]]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    t = Table(rows)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, (0, 0, 0))]))
    doc.build([t])
    return buf.getvalue()


def test_pdf_tableau_d_operations():
    pdf = _table_pdf([
        ["Date", "Opération", "Valeur", "Code ISIN", "Quantité", "Cours", "Frais", "Montant net"],
        ["05/01/2024", "Achat", "AMUNDI MSCI WORLD", "LU1681043599", "4", "450,25", "1,99", "-1 802,99"],
        ["12/03/2024", "Vente", "AMUNDI MSCI WORLD", "LU1681043599", "1", "470,00", "1,99", "468,01"],
        ["20/05/2024", "Dividende", "LVMH", "FR0000121014", "", "", "", "12,50"],
    ])
    a = analyze_file(pdf)
    assert a.format == "pdf-table"
    r = parse_file(pdf)
    assert not r.rejected, r.rejected
    assert [t.type.value for t in r.transactions] == ["buy", "sell", "dividend"]
    assert (r.transactions[0].quantity, r.transactions[0].price, r.transactions[0].fees) == (4, 450.25, 1.99)
    assert r.transactions[2].amount == 12.5


def test_pdf_avis_d_opere():
    pdf = _text_pdf([
        ["AVIS D'OPERE", "Date d'exécution : 15/03/2024", "ACHAT AU COMPTANT",
         "AMUNDI MSCI WORLD UCITS ETF   LU1681043599", "Quantité : 5", "Cours : 452,30 EUR",
         "Montant brut : 2 261,50 EUR", "Courtage : 1,99 EUR", "Montant net : 2 263,49 EUR"],
        ["AVIS D'OPERE", "Date d'exécution : 02/04/2024", "VENTE AU COMPTANT",
         "LVMH MOET HENNESSY   FR0000121014", "Quantité : 2", "Cours : 712,40 EUR",
         "Courtage : 2,50 EUR", "Montant net : 1 422,30 EUR"],
    ])
    a = analyze_file(pdf)
    assert a.format == "pdf-trades"
    r = parse_file(pdf)
    assert not r.rejected, r.rejected
    buy, sell = r.transactions
    assert (buy.type.value, buy.symbol, buy.quantity, buy.price, buy.fees, buy.date.isoformat()) == \
           ("buy", "LU1681043599", 5, 452.3, 1.99, "2024-03-15")
    assert buy.name == "AMUNDI MSCI WORLD UCITS ETF"
    assert (sell.type.value, sell.quantity, sell.price, sell.fees) == ("sell", 2, 712.4, 2.5)


def test_pdf_releve_de_portefeuille():
    pdf = _text_pdf([[
        "RELEVÉ DE PORTEFEUILLE au 30/09/2024",
        "Valeur                         ISIN            Quantité   PRU       Cours     Valorisation",
        "AMUNDI MSCI WORLD   LU1681043599   12   398,45   520,10   6 241,20",
        "APPLE INC           US0378331005   10   150,10   210,00   2 100,00 USD",
        "Total portefeuille                                           8 341,20",
    ]])
    a = analyze_file(pdf)
    assert a.format == "pdf-positions"
    r = parse_file(pdf)
    assert not r.rejected
    w, aapl = r.transactions
    assert (w.type.value, w.quantity, w.price, w.date.isoformat(), w.name) == ("buy", 12, 398.45, "2024-09-30", "AMUNDI MSCI WORLD")
    assert (aapl.quantity, aapl.price, aapl.currency) == (10, 150.1, "USD")
    assert any("prix de revient" in n for n in r.notes)


def test_pdf_scanne_refuse_avec_explication():
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.rect(50, 50, 200, 200, fill=1)
    c.showPage()
    c.save()
    with pytest.raises(ValueError, match="scanné"):
        analyze_file(buf.getvalue())


def test_pdf_sans_operation_reconnue():
    with pytest.raises(ValueError, match="Aucune opération"):
        analyze_file(_text_pdf([["Conditions générales", "Article 1 : objet du contrat"]]))


def test_api_pdf():
    from fastapi.testclient import TestClient

    from atlas.api import app
    client = TestClient(app)
    ok = _text_pdf([["ACHAT", "AMUNDI MSCI WORLD LU1681043599", "Date : 15/03/2024", "Quantité : 5", "Cours : 452,30 EUR"]])
    r = client.post("/imports", files={"file": ("avis.pdf", ok, "application/pdf")})
    assert r.status_code == 200 and len(r.json()["transactions"]) == 1
    scan = io.BytesIO()
    c = canvas.Canvas(scan)
    c.rect(1, 1, 10, 10, fill=1)
    c.save()
    r = client.post("/imports/analyze", files={"file": ("scan.pdf", scan.getvalue(), "application/pdf")})
    assert r.status_code == 400 and "scanné" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Relevé de compte Trade Republic : mise en page reproduite (positions relevées sur un vrai relevé)
# ---------------------------------------------------------------------------
def _tr_statement() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    H = A4[1]

    def at(x, top, text, size=8):
        c.setFont("Helvetica", size)
        c.drawString(x, H - top - size, text)

    def vertical(x, top, word):   # en-têtes « ENTRÉE D'ARGENT » écrits lettre par lettre en décalé
        for i, ch in enumerate(word):
            at(x + 3 * i, top + (6 if i % 2 else 0), ch, 5)

    at(74, 30, "TRADE REPUBLIC BANK GMBH, BRANCH FRANCE")
    at(74, 204, "SYNTHÈSE DU RELEVÉ DE COMPTE")
    for x, t in [(74, "PRODUIT"), (161, "SOLDE DÉBUT"), (271, "ENTRÉE"), (349, "SORTIE"), (462, "SOLDE FIN")]:
        at(x, 242, t)
    for x, t in [(74, "Compte courant"), (161, "0,00 €"), (271, "60,00 €"), (349, "54,45 €"), (496, "5,55 €")]:
        at(x, 257, t)
    at(74, 314, "TRANSACTIONS")
    at(74, 346, "DATE"); at(102, 346, "TYPE"); at(141, 346, "DESCRIPTION"); at(502, 346, "SOLDE")
    vertical(428, 343, "ENTREE"); vertical(459, 343, "SORTIE")
    rows = [
        # (top, date ligne 1, année, type, type ligne 2, description, montant, colonne, solde)
        (364, "03 oct.", "2024", "Virement", "", "Paiement accepté: FR76 à DE16", "50,00", 428, "50,00"),
        (396, "09 oct.", "2024", "Exécution", "d'ordre", "Buy trade CA38149E1016 GOLDMINING INC., quantity: 0.617977",
         "0,55", 459, "49,45"),
        (427, "16 oct.", "2024", "Exécution", "d'ordre", "Savings plan execution US0378331005 APPLE INC., quantity: 0.047136",
         "10,00", 459, "39,45"),
        (459, "22 oct.", "2024", "Exécution", "d'ordre", "Sell trade CA38149E1016 GOLDMINING INC., quantity: 0.617977",
         "0,60", 428, "40,05"),
        (491, "10 nov.", "2024", "Exécution", "d'ordre", "Exécution Achat direct XF000BTC0017 C1012656058",
         "14,97", 459, "25,08"),
        # Comme sur le vrai relevé, « Rendement » est collé au début de la description : « RendementCash Dividend »
        (523, "14 nov.", "2024", "", "", "RendementCash Dividend for ISIN US0378331005", "0,01", 428, "25,09"),
        (555, "20 nov.", "2024", "Virement", "", "Outgoing transfer for Raphaël", "28,93", 459, "-3,84"),
        (587, "02 déc.", "2024", "Virement", "", "Apple Pay Top up", "9,39", 428, "5,55"),
    ]
    for top, d1, year, t1, t2, desc, amount, col, bal in rows:
        at(74, top, d1); at(74, top + 8, year)
        if t1:
            at(102, top + 4, t1)
        if t2:
            at(102, top + 8, t2)
        at(102 if desc.startswith("Rendement") else 141, top + 4, desc)
        at(col, top + 4, amount); at(col + 22, top + 4, "€")
        at(513 - c.stringWidth(bal, "Helvetica", 8), top + 4, bal); at(515, top + 4, "€")
    at(74, 780, "Trade Republic Bank GmbH, Branch France   www.traderepublic.fr")
    c.showPage()
    c.save()
    return buf.getvalue()


def test_pdf_releve_trade_republic():
    pdf = _tr_statement()
    a = analyze_file(pdf)
    assert a.format == "pdf-traderepublic" and a.row_count == 8
    r = parse_file(pdf)
    by_type = [(t.date.isoformat(), t.type.value, t.symbol) for t in r.transactions]
    assert by_type == [
        ("2024-10-03", "deposit", None),
        ("2024-10-09", "buy", "CA38149E1016"),          # sortie d'argent -> achat
        ("2024-10-16", "buy", "US0378331005"),          # plan d'épargne -> achat
        ("2024-10-22", "sell", "CA38149E1016"),         # entrée d'argent -> vente
        ("2024-11-14", "dividend", "US0378331005"),
        ("2024-11-20", "withdrawal", None),
        ("2024-12-02", "deposit", None),
    ]
    buy = r.transactions[1]
    # Quantité au format anglais : 0.617977 (et non 0,617 + 977) ; prix = 0,55 / 0.617977 = 0,88999…
    assert buy.quantity == 0.617977 and abs(buy.price - 0.55 / 0.617977) < 1e-9
    assert buy.name == "GOLDMINING INC."
    assert r.transactions[4].amount == 0.01 and r.transactions[4].name == "APPLE INC."
    # Achat direct de crypto sans quantité : refusé avec une raison explicite
    assert len(r.rejected) == 1 and "Bitcoin" in r.rejected[0].reason and "quantité non indiquée" in r.rejected[0].reason
    # Solde recalculé : 50 - 0,55 - 10 + 0,60 - 14,97 + 0,01 - 28,93 + 9,39 = 5,55 € = solde de fin du relevé
    assert any("5,55 € = solde du relevé" in n for n in r.notes)
