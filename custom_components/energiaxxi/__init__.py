from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import (
    EnergiaxxiConfigEntry,
    EnergiaxxiConsumptionCoordinator,
    EnergiaxxiPriceCoordinator,
    EnergiaxxiRuntimeData,
)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: EnergiaxxiConfigEntry) -> bool:
    consumption = EnergiaxxiConsumptionCoordinator(hass, entry)
    price = EnergiaxxiPriceCoordinator(hass, entry)

    await consumption.async_config_entry_first_refresh()
    # Prices are independent; a failure here must not block setup.
    await price.async_config_entry_first_refresh()

    entry.runtime_data = EnergiaxxiRuntimeData(consumption=consumption, price=price)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EnergiaxxiConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: EnergiaxxiConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
