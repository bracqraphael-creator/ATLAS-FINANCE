import httpx
import pytest

from atlas.core.providers import DemoProvider, EodhdProvider


def test_donnees_de_demo_reproductibles():
    a = DemoProvider().load(["CW8", "AAPL"])
    b = DemoProvider().load(["CW8", "AAPL"])
    assert a.closes["CW8"].equals(b.closes["CW8"])
    assert a.currencies["AAPL"] == "USD"
    assert "fictives" in a.source


# --------------------------------------------------------------------------- EODHD (réponses simulées)
SEARCH = {
    # Apple : cotée à New York (USD), Xetra et Francfort (EUR)
    "US0378331005": [
        {"Code": "AAPL", "Exchange": "US", "Currency": "USD", "ISIN": "US0378331005", "isPrimary": True},
        {"Code": "APC", "Exchange": "F", "Currency": "EUR", "ISIN": "US0378331005"},
        {"Code": "APC", "Exchange": "XETRA", "Currency": "EUR", "ISIN": "US0378331005"},
    ],
    # ETF : la liquidative EUFUND est écartée au profit de la cotation Euronext
    "IE000BI8OT95": [
        {"Code": "IE000BI8OT95", "Exchange": "EUFUND", "Currency": "EUR", "ISIN": "IE000BI8OT95"},
        {"Code": "MWRD", "Exchange": "PA", "Currency": "EUR", "ISIN": "IE000BI8OT95"},
    ],
    # Action londonienne cotée en pence
    "GB0004300496": [{"Code": "PAF", "Exchange": "LSE", "Currency": "GBX", "ISIN": "GB0004300496"}],
    # Résultat d'un autre titre : ne doit pas être retenu (ISIN différent)
    "FR0014001NN8": [{"Code": "XYZ", "Exchange": "PA", "Currency": "EUR", "ISIN": "FR0000000000"}],
}
CLOSES = {
    "APC.XETRA": [("2024-01-02", 170.0), ("2024-01-03", 172.0)],
    "AAPL.US": [("2024-01-02", 185.0), ("2024-01-03", 186.0)],
    "MWRD.PA": [("2024-01-02", 100.0), ("2024-01-03", 101.0)],
    "PAF.LSE": [("2024-01-02", 21.0), ("2024-01-03", 22.0)],
    "BTC-EUR.CC": [("2024-01-02", 40000.0), ("2024-01-03", 41000.0)],
    "USDEUR.FOREX": [("2024-01-02", 0.91), ("2024-01-03", 0.92)],
    "GBPEUR.FOREX": [("2024-01-02", 1.15), ("2024-01-03", 1.16)],
}


def fake_eodhd(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["api_token"] == "cle"
        path = request.url.path.removeprefix("/api/")
        calls.append(path)
        kind, _, arg = path.partition("/")
        if kind == "search":
            return httpx.Response(200, json=SEARCH.get(arg, []))
        if kind == "eod" and arg in CLOSES:
            return httpx.Response(200, json=[{"date": d, "close": c, "adjusted_close": c * 0.9} for d, c in CLOSES[arg]])
        return httpx.Response(404, json={"error": "not found"})
    return handler


@pytest.fixture
def eodhd():
    EodhdProvider.clear_cache()
    calls: list[str] = []
    provider = EodhdProvider("cle", client=httpx.Client(transport=httpx.MockTransport(fake_eodhd(calls))))
    yield provider, calls
    EodhdProvider.clear_cache()


def test_eodhd_resout_les_isin_et_choisit_la_place(eodhd):
    provider, _ = eodhd
    symbols = ["US0378331005", "IE000BI8OT95", "GB0004300496", "XF000BTC0017", "BTC-EUR-TR", "FR0014001NN8"]
    md = provider.load(symbols, {s: "EUR" for s in symbols})
    # Apple achetée en euros : cotation en euros, Xetra préférée à Francfort
    assert md.listings["US0378331005"] == "APC.XETRA" and md.currencies["US0378331005"] == "EUR"
    assert md.listings["IE000BI8OT95"] == "MWRD.PA"
    # Pence -> livres : 22 GBX = 0,22 £, puis converti en euros au taux du jour (1,16)
    assert md.currencies["GB0004300496"] == "GBP"
    assert md.last_price("GB0004300496")[0] == pytest.approx(0.22)
    assert md.last_price_base("GB0004300496") == pytest.approx(0.22 * 1.16)
    # Crypto Trade Republic -> paire en euros ; ligne « en montants » jamais rattachée à un cours
    assert md.listings["XF000BTC0017"] == "BTC-EUR.CC"
    assert not md.has("BTC-EUR-TR")
    # Recherche sans résultat pour cet ISIN : pas de cours (ligne valorisée au prix de revient)
    assert not md.has("FR0014001NN8")
    # Clôture brute, pas la clôture ajustée des dividendes
    assert md.last_price("US0378331005")[0] == 172.0
    assert md.source.startswith("EODHD")


def test_eodhd_titre_achete_en_dollars_cote_aux_etats_unis(eodhd):
    provider, _ = eodhd
    md = provider.load(["US0378331005"], {"US0378331005": "USD"})
    assert md.listings["US0378331005"] == "AAPL.US"
    assert md.last_price_base("US0378331005") == pytest.approx(186.0 * 0.92)


def test_eodhd_cache_entre_deux_modules(eodhd):
    provider, calls = eodhd
    provider.load(["US0378331005"], {"US0378331005": "USD"})
    first = len(calls)
    provider.load(["US0378331005"], {"US0378331005": "USD"})
    assert len(calls) == first          # ni recherche ni cours redemandés


def test_eodhd_erreur_reseau_toleree(eodhd):
    provider, _ = eodhd
    md = provider.load(["US0378331005", "IE000INCONNU1"], {"US0378331005": "USD", "IE000INCONNU1": "EUR"})
    assert md.has("US0378331005")       # un titre introuvable n'empêche pas les autres


def test_load_market_demo_et_sans_cle(monkeypatch):
    from atlas.api import demo_portfolio, load_market
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "eodhd")
    monkeypatch.delenv("MARKET_DATA_API_KEY", raising=False)
    pf = demo_portfolio()
    assert "fictives" in load_market(pf, demo=True).source      # la démo garde ses cours fictifs
    md = load_market(pf)
    assert md.closes == {} and "clé EODHD manquante" in md.source


def test_eodhd_sans_cle():
    with pytest.raises(ValueError):
        EodhdProvider("")


# --------------------------------------------------------------------------- Yahoo (réponses simulées)
YAHOO_SEARCH = {
    "US0378331005": [{"symbol": "AAPL", "exchange": "NMS", "quoteType": "EQUITY"},
                     {"symbol": "APC.DE", "exchange": "GER", "quoteType": "EQUITY"},
                     {"symbol": "APC.F", "exchange": "FRA", "quoteType": "EQUITY"}],
    "IE000BI8OT95": [{"symbol": "MWRD.PA", "exchange": "PAR", "quoteType": "ETF"}],
    "GB0004300496": [{"symbol": "PAF.L", "exchange": "LSE", "quoteType": "EQUITY"}],
    "WisdomTree Physical Swiss Gold": [{"symbol": "LEURRE.PA", "exchange": "PAR", "quoteType": "ETF"},
                                       {"symbol": "SGBS.L", "exchange": "LSE", "quoteType": "ETF"}],
    "CW8": [{"symbol": "CW8.PA", "exchange": "PAR", "quoteType": "ETF"},
            {"symbol": "CW8X.DE", "exchange": "GER", "quoteType": "ETF"}],
}
YAHOO_CHART = {   # ticker : (devise, clôtures) ; deux séances : 02/01/2024 et 03/01/2024
    "APC.DE": ("EUR", [170.0, 172.0]), "AAPL": ("USD", [185.0, 186.0]), "MWRD.PA": ("EUR", [100.0, None]),
    "PAF.L": ("GBp", [21.0, 22.0]), "BTC-EUR": ("EUR", [40000.0, 41000.0]), "CW8.PA": ("EUR", [450.0, 455.0]),
    "LEURRE.PA": ("EUR", [10.0, 10.0]), "SGBS.L": ("USD", [200.0, 202.0]),
    "USDEUR=X": ("EUR", [0.91, 0.92]), "GBPEUR=X": ("EUR", [1.15, 1.16]),
}


def fake_yahoo(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert "Mozilla" in request.headers["user-agent"]
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"quotes": YAHOO_SEARCH.get(request.url.params["q"], [])})
        ticker = request.url.path.rsplit("/", 1)[-1]
        if ticker not in YAHOO_CHART:
            return httpx.Response(404, json={"chart": {"result": None, "error": {"code": "Not Found"}}})
        cur, closes = YAHOO_CHART[ticker]
        return httpx.Response(200, json={"chart": {"error": None, "result": [{
            "meta": {"currency": cur}, "timestamp": [1704207600, 1704294000],   # 02/01 et 03/01/2024, 15 h UTC
            "indicators": {"quote": [{"close": closes}]}}]}})
    return handler


@pytest.fixture
def yahoo():
    from atlas.core.providers import YahooProvider
    YahooProvider.clear_cache()
    calls: list[str] = []
    provider = YahooProvider(client=httpx.Client(transport=httpx.MockTransport(fake_yahoo(calls)),
                                                 headers=YahooProvider.HEADERS))
    yield provider, calls
    YahooProvider.clear_cache()


def test_yahoo_resout_isin_crypto_pence_et_ticker(yahoo):
    provider, calls = yahoo
    syms = ["US0378331005", "IE000BI8OT95", "GB0004300496", "XF000BTC0017", "BTC-EUR-TR", "CW8", "FR0014001NN8"]
    md = provider.load(syms, {s: "EUR" for s in syms})
    assert md.listings["US0378331005"] == "APC.DE"          # achetée en euros : Xetra plutôt que New York
    assert md.listings["CW8"] == "CW8.PA"                   # ticker d'un import CSV, place retrouvée
    assert md.listings["XF000BTC0017"] == "BTC-EUR"
    assert not md.has("BTC-EUR-TR") and not md.has("FR0014001NN8")
    assert md.last_price("GB0004300496")[0] == pytest.approx(0.22)        # 22 pence = 0,22 £
    assert md.last_price_base("GB0004300496") == pytest.approx(0.22 * 1.16)
    assert md.closes["IE000BI8OT95"].tolist() == [100.0]                  # séance sans clôture ignorée
    assert str(md.closes["US0378331005"].index[0].date()) == "2024-01-02"
    n = len(calls)
    provider.load(syms, {s: "EUR" for s in syms})
    assert len(calls) == n                                                # tout vient du cache


def test_yahoo_titre_en_dollars(yahoo):
    provider, _ = yahoo
    md = provider.load(["US0378331005"], {"US0378331005": "USD"})
    assert md.listings["US0378331005"] == "AAPL"
    assert md.last_price_base("US0378331005") == pytest.approx(186.0 * 0.92)
    assert md.source.startswith("Yahoo")


def test_yahoo_repli_par_le_nom_controle_par_le_prix_paye(yahoo):
    from datetime import date
    provider, _ = yahoo
    # ISIN inconnu de la recherche ; achat le 03/01/2024 à 185,84 € = 202 $ × 0,92 : seul SGBS.L est vraisemblable,
    # le leurre (10 €) est écarté par le contrôle à ±20 %
    hints = {"JE00B588CD74": ("WisdomTree Physical Swiss Gold", [(date(2024, 1, 3), 185.84, "EUR")])}
    md = provider.load(["JE00B588CD74"], {"JE00B588CD74": "EUR"}, hints=hints)
    assert md.listings["JE00B588CD74"] == "SGBS.L"
    assert md.last_price_base("JE00B588CD74") == pytest.approx(202 * 0.92)


def test_yahoo_repli_refuse_si_aucun_prix_ne_correspond(yahoo):
    from datetime import date
    provider, _ = yahoo
    hints = {"JE00B588CD74": ("WisdomTree Physical Swiss Gold", [(date(2024, 1, 3), 50.0, "EUR")])}
    md = provider.load(["JE00B588CD74"], {"JE00B588CD74": "EUR"}, hints=hints)
    assert not md.has("JE00B588CD74")      # mieux vaut le prix de revient qu'un cours faux
