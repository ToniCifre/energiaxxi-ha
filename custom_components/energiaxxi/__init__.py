from homeassistant.components.recorder import get_instance
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN
from .coordinator import (
    EnergiaxxiConfigEntry,
    EnergiaxxiConsumptionCoordinator,
    EnergiaxxiPriceCoordinator,
    EnergiaxxiRuntimeData,
)
from .statistics import cost_statistic_id, energy_statistic_id, price_statistic_id

PLATFORMS = [Platform.SENSOR]
SERVICE_CLEAR_STATISTICS = "clear_statistics"


async def async_setup_entry(hass: HomeAssistant, entry: EnergiaxxiConfigEntry) -> bool:
    consumption = EnergiaxxiConsumptionCoordinator(hass, entry)
    price = EnergiaxxiPriceCoordinator(hass, entry)

    await consumption.async_config_entry_first_refresh()
    # Prices are independent; a failure here must not block setup.
    await price.async_config_entry_first_refresh()

    entry.runtime_data = EnergiaxxiRuntimeData(consumption=consumption, price=price)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EnergiaxxiConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: EnergiaxxiConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_CLEAR_STATISTICS):
        return

    async def _handle_clear(call: ServiceCall) -> None:
        ids = {price_statistic_id()}
        for entry in hass.config_entries.async_entries(DOMAIN):
            data = getattr(entry, "runtime_data", None)
            if data is None:
                continue
            for contract_number in data.consumption.contracts:
                ids.add(energy_statistic_id(contract_number))
                ids.add(cost_statistic_id(contract_number))
        get_instance(hass).async_clear_statistics(list(ids))

    hass.services.async_register(DOMAIN, SERVICE_CLEAR_STATISTICS, _handle_clear)
