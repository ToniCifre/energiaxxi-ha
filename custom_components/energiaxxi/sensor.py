import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EnergiaxxiConfigEntry, EnergiaxxiPriceCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnergiaxxiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    price = entry.runtime_data.price
    async_add_entities(
        [
            EnergiaxxiPriceSensor(price),
            EnergiaxxiNextHourPriceSensor(price),
            EnergiaxxiExtremeHourSensor(price, cheapest=True),
            EnergiaxxiExtremeHourSensor(price, cheapest=False),
        ]
    )


def _pvpc_device_info() -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, "pvpc")},
        name="Energiaxxi PVPC",
        manufacturer="CNMC",
        entry_type=DeviceEntryType.SERVICE,
    )


class _PvpcSensor(CoordinatorEntity[EnergiaxxiPriceCoordinator], SensorEntity):
    """Base for PVPC sensors: their value depends on the wall clock, so refresh
    at the top of every hour (the hourly prices are already cached)."""

    def __init__(self, coordinator: EnergiaxxiPriceCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = _pvpc_device_info()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(self.hass, self._hourly_update, minute=0, second=0)
        )

    @callback
    def _hourly_update(self, now) -> None:
        self.async_write_ha_state()


class EnergiaxxiPriceSensor(_PvpcSensor):
    """Current-hour PVPC price. Today's hourly prices (incl. future hours that
    the CNMC already publishes) are exposed as attributes, since Home Assistant
    long-term statistics can only display up to the present."""

    _attr_name = "Energiaxxi PVPC price"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 4
    _attr_unique_id = "pvpc_price"

    def __init__(self, coordinator: EnergiaxxiPriceCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_native_unit_of_measurement = f"{coordinator.currency}/kWh"

    @property
    def native_value(self):
        return self.coordinator.current_price()

    @property
    def extra_state_attributes(self):
        # window of -24h..+24h around the current hour (spans several days), so
        # keys are ISO datetimes rather than "HH:00" which would collide.
        window = self.coordinator.window_prices(24)
        if not window:
            return {}
        attrs = {
            "current": self.coordinator.hour_now().isoformat(),
            "prices": {dt.isoformat(): price for dt, price in window.items()},
        }
        # min/max/average are computed over today's prices only, not the window
        today = list(self.coordinator.todays_prices().values())
        if today:
            attrs["min"] = min(today)
            attrs["max"] = max(today)
            attrs["average"] = round(sum(today) / len(today), 4)
        return attrs


class EnergiaxxiNextHourPriceSensor(_PvpcSensor):
    """PVPC price for the next hour."""

    _attr_name = "Energiaxxi PVPC price next hour"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 4
    _attr_unique_id = "pvpc_price_next_hour"

    def __init__(self, coordinator: EnergiaxxiPriceCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_native_unit_of_measurement = f"{coordinator.currency}/kWh"

    @property
    def native_value(self):
        return self.coordinator.next_hour_price()


class EnergiaxxiExtremeHourSensor(_PvpcSensor):
    """Start time of today's cheapest / most expensive PVPC hour."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: EnergiaxxiPriceCoordinator, cheapest: bool) -> None:
        super().__init__(coordinator)
        self._cheapest = cheapest
        if cheapest:
            self._attr_name = "Energiaxxi PVPC cheapest hour"
            self._attr_unique_id = "pvpc_cheapest_hour"
        else:
            self._attr_name = "Energiaxxi PVPC most expensive hour"
            self._attr_unique_id = "pvpc_most_expensive_hour"

    def _extreme(self):
        prices = self.coordinator.todays_prices()
        if not prices:
            return None
        pick = min if self._cheapest else max
        return pick(prices.items(), key=lambda item: item[1])

    @property
    def native_value(self):
        extreme = self._extreme()
        return extreme[0] if extreme else None

    @property
    def extra_state_attributes(self):
        extreme = self._extreme()
        return {"price": extreme[1]} if extreme else {}
