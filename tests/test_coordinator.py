import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import custom_components.energiaxxi.coordinator as coord_mod
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


# --- _needed_days -----------------------------------------------------------

def _needed_coordinator(history_days):
    coord = EnergiaxxiConsumptionCoordinator.__new__(EnergiaxxiConsumptionCoordinator)
    coord.api = _FakeApi()
    coord.history_days = history_days
    coord.hass = None
    return coord


def _patch_range(monkeypatch, first, last):
    async def fake_range(hass, statistic_id):
        return first, last
    monkeypatch.setattr(coord_mod, "async_get_stat_range", fake_range)


def test_needed_days_full_when_nothing_stored(monkeypatch):
    coord = _needed_coordinator(25)
    _patch_range(monkeypatch, None, None)
    assert asyncio.run(coord._needed_days(["C"])) == 25


def test_needed_days_full_when_widened(monkeypatch):
    coord = _needed_coordinator(60)
    today = datetime.now(TZ)
    # stored data only starts 10 days ago, but we now request 60 -> backfill
    first = (today - timedelta(days=10)).astimezone(timezone.utc)
    last = today.astimezone(timezone.utc)
    _patch_range(monkeypatch, first, last)
    assert asyncio.run(coord._needed_days(["C"])) == 60


def test_needed_days_incremental(monkeypatch):
    coord = _needed_coordinator(25)
    today = datetime.now(TZ)
    first = (today - timedelta(days=25)).astimezone(timezone.utc)
    last = (today - timedelta(days=3)).astimezone(timezone.utc)  # last stored 3d ago
    _patch_range(monkeypatch, first, last)
    # refetch from last stored day forward: 3 days + 1
    assert asyncio.run(coord._needed_days(["C"])) == 4


def test_current_price_reads_current_hour():
    coord = _bare_price_coordinator(_AllDaysPrices())
    now_hour = datetime.now(TZ).replace(minute=0, second=0, microsecond=0)
    coord.prices_by_dt = {now_hour: 0.31, now_hour + timedelta(hours=1): 0.99}
    assert coord.current_price() == 0.31


def test_current_price_none_when_missing():
    coord = _bare_price_coordinator(_AllDaysPrices())
    coord.prices_by_dt = {}
    assert coord.current_price() is None
