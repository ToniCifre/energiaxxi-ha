from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN
from .coordinator import EnergiaxxiCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    coordinator = EnergiaxxiCoordinator(hass, entry.data["username"], entry.data["password"])
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True
