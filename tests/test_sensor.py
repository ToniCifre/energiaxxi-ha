from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from custom_components.energiaxxi.sensor import EnergiaxxiPriceSensor

TZ = ZoneInfo("Europe/Madrid")


class _FakePriceApi:
    tz = TZ


class _FakePriceCoordinator:
    """Enough of EnergiaxxiPriceCoordinator for the sensor properties."""

    currency = "EUR"
    prices = _FakePriceApi()

    def __init__(self, prices_by_dt):
        self.prices_by_dt = prices_by_dt

    def current_price(self):
        now = datetime.now(TZ).replace(minute=0, second=0, microsecond=0)
        return self.prices_by_dt.get(now)


def _sensor(prices_by_dt):
    sensor = EnergiaxxiPriceSensor.__new__(EnergiaxxiPriceSensor)
    sensor.coordinator = _FakePriceCoordinator(prices_by_dt)
    return sensor


def _today_prices(n=24):
    midnight = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return {midnight + timedelta(hours=h): 0.10 + h * 0.01 for h in range(n)}


def test_native_value_is_current_hour_price():
    prices = _today_prices()
    sensor = _sensor(prices)
    now_hour = datetime.now(TZ).replace(minute=0, second=0, microsecond=0)
    assert sensor.native_value == prices[now_hour]


def test_attributes_include_future_hours():
    # full day incl. hours after the current one
    prices = _today_prices(24)
    sensor = _sensor(prices)
    attrs = sensor.extra_state_attributes
    assert len(attrs["prices"]) == 24  # all 24 hours, not just up to now
    assert "23:00" in attrs["prices"]
    assert attrs["min"] == 0.10
    assert attrs["max"] == 0.33


def test_attributes_empty_without_data():
    assert _sensor({}).extra_state_attributes == {}
