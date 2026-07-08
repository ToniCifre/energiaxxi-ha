from homeassistant.core import HomeAssistant

from .coordinator import EnergiaxxiConfigEntry, EnergiaxxiCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: EnergiaxxiConfigEntry) -> bool:
    coordinator = EnergiaxxiCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EnergiaxxiConfigEntry) -> bool:
    return True
