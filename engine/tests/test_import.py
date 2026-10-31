from importlib import resources

import pytest

from atlas.core.importers.standard_csv import _number, parse_standard_csv


def test_format_standard_anglais():
    csv = ("date,type,symbol,name,quantity,price,currency,fees,amount,asset_class,country,sector\n"
           "2024-01-15,buy,CW8,Amundi MSCI World,10,450.20,EUR,1.99,,etf,Monde,Diversifié\n")
    r = parse_standard_csv(csv)
    assert not r.rejected
    t = r.transactions[0]
    assert (t.symbol, t.quantity, t.price, t.fees) == ("CW8", 10, 450.20, 1.99)
    assert r.instruments["CW8"].asset_class.value == "etf"
    assert r.instruments["CW8"].country == "Monde"


def test_format_francais_point_virgule_et_virgule_decimale():
    csv = ("﻿date;type;symbol;quantity;price;currency;fees;asset_class\n"
           "15/01/2024;Achat;MC;2;712,50;eur;2,5;Action\n")
    r = parse_standard_csv(csv)
    assert not r.rejected
    t = r.transactions[0]
    assert t.date.isoformat() == "2024-01-15" and t.type.value == "buy"
    assert t.price == 712.5 and t.fees == 2.5 and t.currency == "EUR"
    assert r.instruments["MC"].asset_class.value == "equity"


@pytest.mark.parametrize("raw,expected", [("1 234,56", 1234.56), ("1,234.56", 1234.56), ("1.234,56", 1234.56),
                                          ("12", 12.0), ("", None)])
def test_lecture_des_nombres(raw, expected):
    assert _number(raw) == expected


def test_lignes_invalides_rejetees_avec_raison():
    csv = ("date,type,symbol,quantity,price,amount\n"
           "2024-01-01,swap,X,1,1,\n"           # type inconnu
           "2024-01-02,buy,,1,10,\n"            # symbole manquant
           "2024-01-03,buy,X,0,10,\n"           # quantité nulle
           "2024-13-40,buy,X,1,10,\n"           # date impossible
           "2024-01-05,dividend,X,,,\n"         # montant manquant
           "2024-01-06,buy,X,1,10,\n")          # seule ligne valide
    r = parse_standard_csv(csv)
    assert len(r.transactions) == 1
    assert [x.line for x in r.rejected] == [2, 3, 4, 5, 6]
    assert "type inconnu" in r.rejected[0].reason


def test_colonnes_obligatoires_manquantes():
    r = parse_standard_csv("symbol,quantity\nX,1\n")
    assert not r.transactions and "colonnes manquantes" in r.rejected[0].reason


def test_fichier_vide():
    assert parse_standard_csv("").transactions == []


def test_fichier_de_demonstration_importe_sans_rejet():
    content = resources.files("atlas").joinpath("data/demo_portfolio.csv").read_bytes()
    r = parse_standard_csv(content)
    assert not r.rejected and len(r.transactions) == 21
