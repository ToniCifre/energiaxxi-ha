import asyncio
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import EnergiaxxiAPI, InvalidCredentialsError
from .statistics import async_import_statistics

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(hours=12)

type EnergiaxxiConfigEntry = ConfigEntry[EnergiaxxiCoordinator]


class EnergiaxxiCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: EnergiaxxiConfigEntry):
        super().__init__(
            hass,
            _LOGGER,
            name="Energiaxxi",
            config_entry=entry,
            update_interval=SCAN_INTERVAL,
        )
        self.api = EnergiaxxiAPI(entry.data["username"], entry.data["password"])

    async def _async_update_data(self):
        try:
            async with asyncio.timeout(45):
                data = await self.hass.async_add_executor_job(self.api.fetch_consumption)
        except InvalidCredentialsError as err:
            raise ConfigEntryAuthFailed from err

        for cid, hourly in data.items():
            await async_import_statistics(self.hass, cid, hourly)

        return data
