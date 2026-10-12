from datetime import date
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


def test_url_requests_whole_local_day(monkeypatch):
    api, calls = _api(monkeypatch, price_response(day="2026-07-07"))
    api.get_day_prices(date(2026, 7, 7))
    assert calls[0].startswith(PvpcPriceAPI.BASE_URL)
    assert "start_date=2026-07-07T00:00&end_date=2026-07-07T23:59" in calls[0]
    assert "time_trunc=hour" in calls[0]


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
    api, _ = _api(monkeypatch, {"included": []})
    with pytest.raises(PvpcPriceError):
        api.get_day_prices(date(2026, 6, 29))


def test_converts_mwh_to_kwh(monkeypatch):
    api, _ = _api(monkeypatch, price_response(base=0.221))
    assert api.get_day_prices(date(2026, 6, 29))[0] == pytest.approx(0.221)


def test_ignores_values_outside_requested_day(monkeypatch):
    resp = price_response(day="2026-06-29")
    resp["included"][0]["attributes"]["values"].append(
        {"value": 999.0, "datetime": "2026-06-30T00:00:00.000+02:00"}
    )
    api, _ = _api(monkeypatch, resp)
    prices = api.get_day_prices(date(2026, 6, 29))
    assert len(prices) == 24
    assert prices[0] == pytest.approx(0.20)


def test_missing_pvpc_indicator_raises(monkeypatch):
    api, _ = _api(monkeypatch, {"included": [{"type": "Precio mercado spot", "id": "600"}]})
    with pytest.raises(PvpcPriceError):
        api.get_day_prices(date(2026, 6, 29))
