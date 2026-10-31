import httpx
import pytest

from atlas.core.providers import DemoProvider, EodhdProvider


def test_donnees_de_demo_reproductibles():
    a = DemoProvider().load(["CW8", "AAPL"])
    b = DemoProvider().load(["CW8", "AAPL"])
    assert a.closes["CW8"].equals(b.closes["CW8"])
    assert a.currencies["AAPL"] == "USD"
    assert "fictives" in a.source


def test_eodhd_lit_les_clotures_ajustees():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["api_token"] == "cle"
        if "FOREX" in request.url.path:
            return httpx.Response(200, json=[{"date": "2024-01-02", "close": 0.91}])
        return httpx.Response(200, json=[
            {"date": "2024-01-02", "close": 10, "adjusted_close": 9.5},
            {"date": "2024-01-03", "close": 11, "adjusted_close": 10.5},
        ])

    provider = EodhdProvider("cle", client=httpx.Client(transport=httpx.MockTransport(handler)))
    md = provider.load(["AAPL.US"], {"AAPL.US": "USD"})
    assert md.closes["AAPL.US"].tolist() == [9.5, 10.5]
    assert md.fx_rate("USD", md.as_of) == pytest.approx(0.91)
    assert md.last_price_base("AAPL.US") == pytest.approx(10.5 * 0.91)


def test_eodhd_sans_cle():
    with pytest.raises(ValueError):
        EodhdProvider("")
