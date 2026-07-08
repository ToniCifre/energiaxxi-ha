from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.energiaxxi.prices import PvpcPriceAPI, PvpcPriceError
from conftest import FakeResponse, price_response

TZ = ZoneInfo("Europe/Madrid")


def _api(monkeypatch, response, status=200):
    api = PvpcPriceAPI(TZ)
    calls = []

    def fake_get(url):
        calls.append(url)
        return FakeResponse(response, status)

    monkeypatch.setattr(api.session, "get", fake_get)
    return api, calls


def test_timestamp_in_url_is_midnight_madrid_ms(monkeypatch):
    api, calls = _api(monkeypatch, price_response())
    api.get_day_prices(date(2026, 7, 7))
    expected = int(datetime(2026, 7, 7, tzinfo=TZ).timestamp() * 1000)
    assert f"/{expected}-1-1" in calls[0]
    assert expected == 1783375200000


def test_parses_prices_by_hour(monkeypatch):
    api, _ = _api(monkeypatch, price_response(base=0.20))
    prices = api.get_day_prices(date(2026, 6, 29))
    assert len(prices) == 24
    assert prices[0] == pytest.approx(0.20)
    assert prices[23] == pytest.approx(0.223)


def test_caches_per_day(monkeypatch):
    api, calls = _api(monkeypatch, price_response())
    p1 = api.get_day_prices(date(2026, 6, 29))
    p2 = api.get_day_prices(date(2026, 6, 29))
    assert p1 is p2
    assert len(calls) == 1  # second call served from cache


def test_http_error_raises(monkeypatch):
    api, _ = _api(monkeypatch, None, status=500)
    with pytest.raises(PvpcPriceError):
        api.get_day_prices(date(2026, 6, 29))


def test_empty_prices_raise(monkeypatch):
    api, _ = _api(monkeypatch, {"preciosHora": []})
    with pytest.raises(PvpcPriceError):
        api.get_day_prices(date(2026, 6, 29))
