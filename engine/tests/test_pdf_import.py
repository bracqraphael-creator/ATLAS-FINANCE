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
