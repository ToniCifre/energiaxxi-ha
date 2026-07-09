from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from custom_components.energiaxxi.sensor import (
    EnergiaxxiExtremeHourSensor,
    EnergiaxxiNextHourPriceSensor,
    EnergiaxxiPriceSensor,
)

TZ = ZoneInfo("Europe/Madrid")


class _FakePriceApi:
    tz = TZ


class _FakePriceCoordinator:
    """Enough of EnergiaxxiPriceCoordinator for the sensor properties."""

    currency = "EUR"
    prices = _FakePriceApi()

    def __init__(self, prices_by_dt):
        self.prices_by_dt = prices_by_dt

    def hour_now(self):
        return datetime.now(TZ).replace(minute=0, second=0, microsecond=0)

    def current_price(self):
        return self.prices_by_dt.get(self.hour_now())

    def next_hour_price(self):
        return self.prices_by_dt.get(self.hour_now() + timedelta(hours=1))

    def todays_prices(self):
        today = datetime.now(TZ).date()
        return {dt: p for dt, p in self.prices_by_dt.items() if dt.date() == today}

    def window_prices(self, hours=12):
        now = self.hour_now()
        out = {}
        for offset in range(-hours, hours + 1):
            dt = now + timedelta(hours=offset)
            if dt in self.prices_by_dt:
                out[dt] = self.prices_by_dt[dt]
        return dict(sorted(out.items()))


def _make(cls, prices_by_dt, *args):
    sensor = cls.__new__(cls)
    sensor.coordinator = _FakePriceCoordinator(prices_by_dt)
    for name, val in args:
        setattr(sensor, name, val)
    return sensor


def _sensor(prices_by_dt):
    return _make(EnergiaxxiPriceSensor, prices_by_dt)


def _today_prices(n=24):
    midnight = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return {midnight + timedelta(hours=h): 0.10 + h * 0.01 for h in range(n)}


def test_native_value_is_current_hour_price():
    prices = _today_prices()
    sensor = _sensor(prices)
    now_hour = datetime.now(TZ).replace(minute=0, second=0, microsecond=0)
    assert sensor.native_value == prices[now_hour]


def test_attributes_window_uses_iso_keys():
    now = datetime.now(TZ).replace(minute=0, second=0, microsecond=0)
    # -12h..+12h around now, spanning two days
    prices = {now + timedelta(hours=o): 0.10 + (o + 12) * 0.01 for o in range(-12, 13)}
    sensor = _sensor(prices)
    attrs = sensor.extra_state_attributes

    assert len(attrs["prices"]) == 25  # only the ±12h we provided
    # keys are ISO datetimes, covering past and future
    assert attrs["current"] == now.isoformat()
    assert (now + timedelta(hours=12)).isoformat() in attrs["prices"]
    assert (now - timedelta(hours=12)).isoformat() in attrs["prices"]
    assert attrs["min"] == 0.10
    assert round(attrs["max"], 2) == 0.34


def test_attributes_empty_without_data():
    assert _sensor({}).extra_state_attributes == {}


def test_next_hour_price():
    prices = _today_prices()
    sensor = _make(EnergiaxxiNextHourPriceSensor, prices)
    next_hour = datetime.now(TZ).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    assert sensor.native_value == prices.get(next_hour)


def test_cheapest_and_most_expensive_hour():
    prices = _today_prices(24)  # increasing 0.10..0.33
    cheapest = _make(EnergiaxxiExtremeHourSensor, prices, ("_cheapest", True))
    expensive = _make(EnergiaxxiExtremeHourSensor, prices, ("_cheapest", False))

    midnight = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    assert cheapest.native_value == midnight          # hour 0 = 0.10
    assert cheapest.extra_state_attributes["price"] == 0.10
    assert expensive.native_value == midnight + timedelta(hours=23)  # hour 23 = 0.33
    assert expensive.extra_state_attributes["price"] == 0.33


def test_extreme_hour_none_without_data():
    sensor = _make(EnergiaxxiExtremeHourSensor, {}, ("_cheapest", True))
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}
