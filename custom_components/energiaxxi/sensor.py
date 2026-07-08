import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .common import contract_location
from .const import DOMAIN
from .coordinator import EnergiaxxiConfigEntry, EnergiaxxiConsumptionCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnergiaxxiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.consumption
    async_add_entities(
        EnergiaxxiLastReadingSensor(coordinator, contract_number)
        for contract_number in coordinator.contracts
    )


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
