import asyncio
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    EnergiaxxiAPI,
    EnergiaxxiApiError,
    IncapsulaDetectedError,
    InvalidCredentialsError,
)
from .common import contract_location
from .const import (
    CONF_HISTORY_DAYS,
    CONF_SCAN_INTERVAL_HOURS,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_SCAN_INTERVAL_HOURS,
)
from .statistics import async_import_statistics

_LOGGER = logging.getLogger(__name__)

type EnergiaxxiConfigEntry = ConfigEntry[EnergiaxxiCoordinator]


class EnergiaxxiCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: EnergiaxxiConfigEntry):
        self.history_days = entry.options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS)
        scan_hours = entry.options.get(CONF_SCAN_INTERVAL_HOURS, DEFAULT_SCAN_INTERVAL_HOURS)
        super().__init__(
            hass,
            _LOGGER,
            name="Energiaxxi",
            config_entry=entry,
            update_interval=timedelta(hours=scan_hours),
        )
        self.api = EnergiaxxiAPI(entry.data["username"], entry.data["password"])
        # contractNumber -> contract dict (metadata for the device/sensors)
        self.contracts: dict[str, dict] = {}

    def _fetch(self) -> dict:
        """Blocking API access, runs in the executor."""
        contracts = self.api.contracts()
        consumption = self.api.fetch_consumption(self.history_days)
        return {"contracts": contracts, "consumption": consumption}

    async def _async_update_data(self):
        try:
            async with asyncio.timeout(60):
                result = await self.hass.async_add_executor_job(self._fetch)
        except InvalidCredentialsError as err:
            raise ConfigEntryAuthFailed from err
        except (IncapsulaDetectedError, EnergiaxxiApiError) as err:
            raise UpdateFailed(str(err)) from err

        self.contracts = {c["contractNumber"]: c for c in result["contracts"]}
        consumption = result["consumption"]

        for cid, hourly in consumption.items():
            location = contract_location(self.contracts.get(cid, {"contractNumber": cid}))
            await async_import_statistics(
                self.hass, cid, hourly, name=f"Energiaxxi {location} Energy"
            )

        return consumption
