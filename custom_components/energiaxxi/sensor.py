import logging
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .common import contract_location
from .const import DOMAIN
from .coordinator import (
    EnergiaxxiConfigEntry,
    EnergiaxxiConsumptionCoordinator,
    EnergiaxxiPriceCoordinator,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnergiaxxiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    consumption = entry.runtime_data.consumption
    entities = [
        EnergiaxxiLastReadingSensor(consumption, contract_number)
        for contract_number in consumption.contracts
    ]
    entities.append(EnergiaxxiPriceSensor(entry.runtime_data.price))
    async_add_entities(entities)


class EnergiaxxiLastReadingSensor(CoordinatorEntity[EnergiaxxiConsumptionCoordinator], SensorEntity):
    """Timestamp of the most recent hourly reading imported for a contract.

    The consumption itself is exposed as an external statistic (used by the
    Energy dashboard); this diagnostic sensor exists to anchor a device and
    surface contract metadata.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "last_reading"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: EnergiaxxiConsumptionCoordinator, contract_number: str) -> None:
        super().__init__(coordinator)
        self._contract_number = contract_number
        self._attr_unique_id = f"{contract_number}_last_reading"

        contract = coordinator.contracts.get(contract_number, {})
        cups = contract.get("cups") or contract_number
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(cups))},
            name=f"Energiaxxi {contract_location(contract)}",
            manufacturer="Endesa",
            model=contract.get("rate"),
            serial_number=str(cups),
        )

    @property
    def native_value(self):
        rows = self.coordinator.data.get(self._contract_number) if self.coordinator.data else None
        if not rows:
            return None
        return max(row["datetime"] for row in rows)

    @property
    def extra_state_attributes(self):
        contract = self.coordinator.contracts.get(self._contract_number, {})
        return {
            "contract_number": self._contract_number,
            "cups": contract.get("cups"),
            "tariff": contract.get("specificTariff"),
            "rate": contract.get("rate"),
            "power_kw": contract.get("power"),
        }


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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "pvpc")},
            name="Energiaxxi PVPC",
            manufacturer="CNMC",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self):
        return self.coordinator.current_price()

    @property
    def extra_state_attributes(self):
        today = datetime.now(self.coordinator.prices.tz).date()
        todays = {
            dt: price
            for dt, price in self.coordinator.prices_by_dt.items()
            if dt.date() == today
        }
        if not todays:
            return {}
        prices = dict(sorted(todays.items()))
        values = list(prices.values())
        return {
            "prices": {dt.strftime("%H:%M"): price for dt, price in prices.items()},
            "min": min(values),
            "max": max(values),
            "average": round(sum(values) / len(values), 4),
        }
