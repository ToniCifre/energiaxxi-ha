import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
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


class EnergiaxxiPriceSensor(CoordinatorEntity[EnergiaxxiPriceCoordinator], SensorEntity):
    """Current-hour PVPC price. Today's hourly prices (incl. future hours that
    the CNMC already publishes) are exposed as attributes, since Home Assistant
    long-term statistics can only display up to the present."""

    _attr_has_entity_name = True
    _attr_translation_key = "pvpc_price"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 4
    _attr_unique_id = "pvpc_price"

    def __init__(self, coordinator: EnergiaxxiPriceCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_native_unit_of_measurement = f"{coordinator.currency}/kWh"
        self._attr_device_info = _pvpc_device_info()

    @property
    def native_value(self):
        return self.coordinator.current_price()

    @property
    def extra_state_attributes(self):
        prices = dict(sorted(self.coordinator.todays_prices().items()))
        if not prices:
            return {}
        values = list(prices.values())
        return {
            "prices": {dt.strftime("%H:%M"): price for dt, price in prices.items()},
            "min": min(values),
            "max": max(values),
            "average": round(sum(values) / len(values), 4),
        }


class EnergiaxxiNextHourPriceSensor(CoordinatorEntity[EnergiaxxiPriceCoordinator], SensorEntity):
    """PVPC price for the next hour."""

    _attr_has_entity_name = True
    _attr_translation_key = "pvpc_price_next_hour"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 4
    _attr_unique_id = "pvpc_price_next_hour"

    def __init__(self, coordinator: EnergiaxxiPriceCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_native_unit_of_measurement = f"{coordinator.currency}/kWh"
        self._attr_device_info = _pvpc_device_info()

    @property
    def native_value(self):
        return self.coordinator.next_hour_price()


class EnergiaxxiExtremeHourSensor(CoordinatorEntity[EnergiaxxiPriceCoordinator], SensorEntity):
    """Start time of today's cheapest / most expensive PVPC hour."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: EnergiaxxiPriceCoordinator, cheapest: bool) -> None:
        super().__init__(coordinator)
        self._cheapest = cheapest
        self._attr_translation_key = (
            "pvpc_cheapest_hour" if cheapest else "pvpc_most_expensive_hour"
        )
        self._attr_unique_id = (
            "pvpc_cheapest_hour" if cheapest else "pvpc_most_expensive_hour"
        )
        self._attr_device_info = _pvpc_device_info()

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
