"""Import universel : formats variés de courtiers et de logiciels."""

import io

import pytest
from openpyxl import Workbook

from atlas.core.importers import analyze_file, parse_file
from atlas.core.importers.universal import parse_date, parse_number, parse_type

# Structure de l'export « Transactions » DEGIRO (19 colonnes, devises dans des colonnes sans titre).
# Valeurs fictives.
DEGIRO_FR = (
    'Date,Heure,Produit,Code ISIN,Bourse de référence,Lieu d\'exécution,Quantité,Cours,,Montant devise locale,,'
    'Montant,,Taux de change,Frais de courtage,,Montant négocié,,ID Ordre\n'
    '"28-10-2024","15:31","APPLE INC. - COMMON ST","US0378331005","NDQ","XNAS","10","231,50","USD","-2315,00","USD",'
    '"-2135,47","EUR","1,0841","-2,00","EUR","-2137,47","EUR","a1"\n'
    '"02-09-2024","09:05","AMUNDI MSCI WORLD UCITS ETF","LU1681043599","EPA","XPAR","3","520,10","EUR","-1560,30",'
    '"EUR","-1560,30","EUR","","-1,00","EUR","-1561,30","EUR","b2"\n'
    '"15-11-2024","16:02","APPLE INC. - COMMON ST","US0378331005","NDQ","XNAS","-4","240,00","USD","960,00","USD",'
    '"887,06","EUR","1,0822","-2,00","EUR","885,06","EUR","c3"\n'
)

DEGIRO_EN = (
    "Date,Time,Product,ISIN,Reference exchange,Venue,Quantity,Price,,Local value,,Value,,Exchange rate,"
    "Transaction and/or third,,Total,,Order ID\n"
    '02-09-2024,09:05,AMUNDI MSCI WORLD,LU1681043599,EPA,XPAR,3,"520.10",EUR,"-1560.30",EUR,"-1560.30",EUR,,'
    '"-1.00",EUR,"-1561.30",EUR,b2\n'
)


def test_degiro_francais_reconnu():
    a = analyze_file(DEGIRO_FR.encode())
    assert a.format == "degiro" and not a.missing
    r = parse_file(DEGIRO_FR.encode())
    assert not r.rejected
    buys = [t for t in r.transactions if t.type.value == "buy"]
    sells = [t for t in r.transactions if t.type.value == "sell"]
    fees = [t for t in r.transactions if t.type.value == "fee"]
    apple = buys[0]
    assert (apple.symbol, apple.quantity, apple.price, apple.currency) == ("US0378331005", 10, 231.5, "USD")
    assert apple.fees == 0                      # frais en EUR sur un titre en USD : comptés à part
    assert sells[0].quantity == 4 and sells[0].price == 240
    etf = buys[1]
    assert etf.fees == 1 and etf.currency == "EUR"   # même devise : frais inclus dans le prix de revient
    assert [f.amount for f in fees] == [2.0, 2.0] and all(f.currency == "EUR" for f in fees)
    assert r.instruments["US0378331005"].name == "APPLE INC. - COMMON ST"


def test_degiro_anglais_reconnu():
    a = analyze_file(DEGIRO_EN.encode())
    assert a.format == "degiro"
    t = parse_file(DEGIRO_EN.encode()).transactions[0]
    assert (t.quantity, t.price, t.fees) == (3, 520.10, 1.0)


def test_releve_bancaire_avec_libelle_et_titres_en_tete():
    csv = ("Relevé du compte PEA\n\n"
           "Date opération;Libellé;Code ISIN;Quantité;Cours;Montant;Devise\n"
           "05/01/2024;ACHAT COMPTANT AMUNDI MSCI WORLD;LU1681043599;4;450,25;-1801,00;EUR\n"
           "12/03/2024;VENTE COMPTANT AMUNDI MSCI WORLD;LU1681043599;1;470,00;470,00;EUR\n"
           "20/05/2024;DIVIDENDE LVMH;FR0000121014;;;12,50;EUR\n"
           "03/06/2024;VIREMENT INTERNE;;;;500,00;EUR\n"
           "04/06/2024;VIREMENT VERS COMPTE COURANT;;;;-200,00;EUR\n").encode("cp1252")
    r = parse_file(csv)
    assert not r.rejected, r.rejected
    assert [t.type.value for t in r.transactions] == ["buy", "sell", "dividend", "deposit", "withdrawal"]
    assert r.transactions[1].quantity == 1          # « VENTE » lu dans le libellé malgré une quantité positive
    assert r.transactions[2].amount == 12.5
    assert r.transactions[0].name == "AMUNDI MSCI WORLD"   # mot d'opération retiré du libellé
    assert r.transactions[3].symbol is None and r.transactions[4].amount == 200


def test_export_allemand():
    csv = ("Datum;Typ;Wertpapier;ISIN;Stück;Kurs;Gebühren;Währung\n"
           "01.03.2024;Kauf;iShares Core MSCI World;IE00B4L5Y983;5;85,10;1,00;EUR\n"
           "01.06.2024;Verkauf;iShares Core MSCI World;IE00B4L5Y983;2;90,00;1,00;EUR\n").encode()
    r = parse_file(csv)
    assert not r.rejected
    assert [(t.type.value, t.quantity, t.price) for t in r.transactions] == [("buy", 5, 85.1), ("sell", 2, 90.0)]


def test_export_crypto_anglais():
    csv = ("Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,Spot Price at Transaction,"
           "Fees and/or Spread\n"
           "2024-03-01T10:00:00Z,Buy,BTC,0.01,EUR,58000,1.49\n"
           "2024-04-01T10:00:00Z,Sell,BTC,0.005,EUR,61000,0.99\n").encode()
    a = analyze_file(csv)
    assert {"date", "type", "symbol", "quantity", "price", "currency", "fees"} <= set(a.mapping)
    r = parse_file(csv)
    assert not r.rejected
    assert (r.transactions[0].symbol, r.transactions[0].price, r.transactions[0].fees) == ("BTC", 58000, 1.49)


def test_sans_colonne_type_le_signe_decide():
    csv = "Date,Symbol,Quantity,Price\n2024-01-02,AAPL,10,180\n2024-02-02,AAPL,-3,190\n".encode()
    r = parse_file(csv)
    assert [t.type.value for t in r.transactions] == ["buy", "sell"]
    assert r.notes and "signe" in r.notes[0]


def test_prix_deduit_du_montant():
    csv = "Date,Type,Symbol,Quantity,Amount\n2024-01-02,Achat,CW8,4,-1800\n".encode()
    t = parse_file(csv).transactions[0]
    assert t.price == pytest.approx(450)


def test_fichier_excel():
    wb = Workbook()
    ws = wb.active
    ws.append(["Date", "Opération", "Titre", "Quantité", "Prix", "Frais"])
    from datetime import date
    ws.append([date(2024, 2, 1), "Achat", "LVMH", 2, 700.5, 2.5])
    buf = io.BytesIO()
    wb.save(buf)
    r = parse_file(buf.getvalue(), "export.xlsx")
    assert not r.rejected
    t = r.transactions[0]
    assert (t.date.isoformat(), t.symbol, t.quantity, t.price, t.fees) == ("2024-02-01", "LVMH", 2, 700.5, 2.5)


def test_correspondance_corrigee_par_l_utilisateur():
    csv = "Jour,Sens,Valeur,Nb,PU\n2024-01-02,A,CW8,3,450\n".encode()
    # « Sens » contient « A » (non reconnu) : l'utilisateur retire la colonne type ; le signe décide.
    r = parse_file(csv, mapping={"date": 0, "symbol": 2, "quantity": 3, "price": 4})
    assert r.format == "custom" and len(r.transactions) == 1 and r.transactions[0].type.value == "buy"


def test_type_inconnu_signale_la_ligne():
    csv = "Date,Type,Symbol,Quantity,Price\n2024-01-02,Echange de titres,CW8,3,450\n".encode()
    r = parse_file(csv)
    assert not r.transactions and "non reconnu" in r.rejected[0].reason


def test_aucune_colonne_de_date():
    a = analyze_file(b"Symbol,Quantity,Price\nAAPL,1,100\n")
    assert "date" in a.missing


@pytest.mark.parametrize("raw,expected", [
    ("1 234,56", 1234.56), ("1,234.56", 1234.56), ("1.234,56", 1234.56), ("-2,00", -2.0), ("(15.20)", -15.2),
    ("12,50 €", 12.5), ("", None), (3, 3.0), ("1,000,000", 1000000.0),
])
def test_nombres(raw, expected):
    assert parse_number(raw) == expected


@pytest.mark.parametrize("raw", ["2024-03-01", "01/03/2024", "01-03-2024", "01.03.2024", "2024-03-01T10:00:00Z",
                                 "2024-03-01 10:00:00", "01/03/2024 09:30"])
def test_dates(raw):
    assert parse_date(raw).isoformat() == "2024-03-01"


@pytest.mark.parametrize("raw,expected", [
    ("ACHAT COMPTANT", "buy"), ("Kauf", "buy"), ("Sell", "sell"), ("VENTE", "sell"), ("Dividende", "dividend"),
    ("Droits de garde", "fee"), ("Versement", "deposit"), ("Retrait", "withdrawal"), ("Plan d'investissement", "buy"),
    ("Truc", None),
])
def test_types(raw, expected):
    assert parse_type(raw) == expected


# --------------------------------------------------------------------------- Plusieurs comptes dans un fichier
def test_enveloppe_devinee_depuis_le_nom_du_compte():
    from atlas.core.importers.universal import guess_wrapper
    cases = {"Compte PEA": "pea", "PEA-PME": "pea_pme", "PEA PME Boursorama": "pea_pme", "Compte courant": "cto",
             "Compte-titres ordinaire": "cto", "CTO": "cto", "Assurance vie Linxea": "assurance_vie",
             "PER individuel": "per", "Portefeuille crypto": "crypto", "Livret A": "other"}
    assert {k: guess_wrapper(k) for k in cases} == cases


def test_csv_avec_colonne_compte_repartit_les_operations():
    from atlas.core.importers import parse_file
    csv = ("Date;Compte;Opération;ISIN;Libellé;Quantité;Cours\n"
           "02/01/2024;PEA;Achat;FR0011550185;BNP S&P 500;10;20\n"
           "03/01/2024;Compte-titres;Achat;US0378331005;Apple;1;180\n"
           "04/01/2024;PEA;Achat;FR0011550185;BNP S&P 500;5;21\n").encode()
    r = parse_file(csv)
    assert not r.rejected
    assert [t.account for t in r.transactions] == ["PEA", "Compte-titres", "PEA"]
    assert [(a.label, a.wrapper, a.count, a.suggested_name) for a in r.accounts] == [
        ("PEA", "pea", 2, "PEA"), ("Compte-titres", "cto", 1, "Compte-titres")]
    assert any("2 comptes distincts" in n for n in r.notes)


def test_fichier_sans_compte():
    from atlas.core.importers import parse_file
    r = parse_file(b"Date;Operation;ISIN;Quantite;Cours\n02/01/2024;Achat;FR0011550185;10;20\n")
    assert r.accounts == [] and r.transactions[0].account is None
