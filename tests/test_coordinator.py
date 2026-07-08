from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from custom_components.energiaxxi.coordinator import (
    EnergiaxxiConsumptionCoordinator,
    EnergiaxxiPriceCoordinator,
)
from custom_components.energiaxxi.prices import PvpcPriceError

TZ = ZoneInfo("Europe/Madrid")


class _FakePrices:
    tz = TZ

    def __init__(self, by_day, raise_days=()):
        self._by_day = by_day
        self._raise = set(raise_days)

    def get_day_prices(self, day):
        if day in self._raise:
            raise PvpcPriceError("boom")
        return self._by_day.get(day, {})


class _FakeApi:
    tz = TZ


def _bare_coordinator(prices):
    coord = EnergiaxxiConsumptionCoordinator.__new__(EnergiaxxiConsumptionCoordinator)
    coord.prices = prices
    coord.api = _FakeApi()
    return coord


def _bare_price_coordinator(prices):
    coord = EnergiaxxiPriceCoordinator.__new__(EnergiaxxiPriceCoordinator)
    coord.prices = prices
    return coord


def test_compute_cost_multiplies_price():
    day = datetime(2026, 6, 24, tzinfo=TZ).date()
    prices = _FakePrices({day: {h: 0.20 for h in range(24)}})
    coord = _bare_coordinator(prices)

    base = datetime(2026, 6, 24, 0, 0, tzinfo=TZ)
    hourly = [{"datetime": base + timedelta(hours=h), "kwh": 0.5} for h in range(24)]

    cost_rows = coord._compute_cost(hourly)
    assert len(cost_rows) == 24
    assert cost_rows[0]["cost"] == 0.10  # 0.5 * 0.20
    assert round(sum(r["cost"] for r in cost_rows), 4) == 2.4


def test_compute_cost_skips_missing_hour_price():
    day = datetime(2026, 6, 24, tzinfo=TZ).date()
    prices = _FakePrices({day: {0: 0.20}})  # only hour 0 priced
    coord = _bare_coordinator(prices)

    base = datetime(2026, 6, 24, 0, 0, tzinfo=TZ)
    hourly = [{"datetime": base + timedelta(hours=h), "kwh": 1.0} for h in range(3)]

    cost_rows = coord._compute_cost(hourly)
    assert len(cost_rows) == 1
    assert cost_rows[0]["cost"] == 0.20


def test_compute_cost_handles_price_error():
    day = datetime(2026, 6, 24, tzinfo=TZ).date()
    prices = _FakePrices({}, raise_days={day})
    coord = _bare_coordinator(prices)

    base = datetime(2026, 6, 24, 0, 0, tzinfo=TZ)
    hourly = [{"datetime": base, "kwh": 1.0}]

    assert coord._compute_cost(hourly) == []  # error swallowed, no crash


class _AllDaysPrices:
    tz = TZ

    def __init__(self, hours=24, raise_all=False):
        self._hours = hours
        self._raise = raise_all

    def get_day_prices(self, day):
        if self._raise:
            raise PvpcPriceError("down")
        return {h: 0.20 for h in range(self._hours)}


def test_fetch_prices_covers_requested_days():
    coord = _bare_price_coordinator(_AllDaysPrices())
    points = coord._fetch_prices(3)
    assert len(points) == 72  # 3 days * 24 hours
    # tz-aware, sorted-able, distinct hours
    assert all(dt.tzinfo is not None for dt, _ in points)
    assert len({dt for dt, _ in points}) == 72


def test_fetch_prices_swallows_errors():
    coord = _bare_price_coordinator(_AllDaysPrices(raise_all=True))
    assert coord._fetch_prices(3) == []
