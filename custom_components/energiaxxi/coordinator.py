import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

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
    CONF_CONSUMPTION_INTERVAL_HOURS,
    CONF_HISTORY_DAYS,
    CONF_PRICE_DAYS,
    CONF_PRICE_INTERVAL_HOURS,
    DEFAULT_CONSUMPTION_INTERVAL_HOURS,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_PRICE_DAYS,
    DEFAULT_PRICE_INTERVAL_HOURS,
    interval_option,
)
from .prices import PvpcPriceAPI, PvpcPriceError
from .statistics import (
    async_import_cost_statistics,
    async_import_energy_statistics,
    async_import_price_statistics,
)

_LOGGER = logging.getLogger(__name__)

type EnergiaxxiConfigEntry = ConfigEntry[EnergiaxxiRuntimeData]


@dataclass
class EnergiaxxiRuntimeData:
    consumption: "EnergiaxxiConsumptionCoordinator"
    price: "EnergiaxxiPriceCoordinator"


class EnergiaxxiPriceCoordinator(DataUpdateCoordinator):
    """Imports national PVPC hourly prices, independent of the Endesa account."""

    def __init__(self, hass: HomeAssistant, entry: EnergiaxxiConfigEntry):
        interval = interval_option(
            entry.options, CONF_PRICE_INTERVAL_HOURS, DEFAULT_PRICE_INTERVAL_HOURS
        )
        super().__init__(
            hass,
            _LOGGER,
            name="Energiaxxi PVPC prices",
            config_entry=entry,
            update_interval=timedelta(hours=interval),
        )
        self.prices = PvpcPriceAPI()
        self.currency = hass.config.currency
        self.price_days = entry.options.get(CONF_PRICE_DAYS, DEFAULT_PRICE_DAYS)

    def _fetch_prices(self, price_days: int) -> list[tuple]:
        """Fetch the last `price_days` days of hourly PVPC prices. Blocking."""
        points = []
        today = datetime.now(self.prices.tz).date()
        for i in range(price_days):
            day = today - timedelta(days=i)
            try:
                prices = self.prices.get_day_prices(day)
            except PvpcPriceError as err:
                _LOGGER.warning("Skipping prices for %s: %s", day, err)
                continue
            for hour, price in prices.items():
                dt = datetime(day.year, day.month, day.day, hour, tzinfo=self.prices.tz)
                points.append((dt, price))
        return points

    async def _async_update_data(self):
        points = await self.hass.async_add_executor_job(self._fetch_prices, self.price_days)
        if points:
            await async_import_price_statistics(
                self.hass, points, self.currency, name="Energiaxxi PVPC Price"
            )
        return points


class EnergiaxxiConsumptionCoordinator(DataUpdateCoordinator):
    """Imports per-contract hourly energy and (for PVPC contracts) cost."""

    def __init__(self, hass: HomeAssistant, entry: EnergiaxxiConfigEntry):
        interval = interval_option(
            entry.options, CONF_CONSUMPTION_INTERVAL_HOURS, DEFAULT_CONSUMPTION_INTERVAL_HOURS
        )
        super().__init__(
            hass,
            _LOGGER,
            name="Energiaxxi consumption",
            config_entry=entry,
            update_interval=timedelta(hours=interval),
        )
        self.api = EnergiaxxiAPI(entry.data["username"], entry.data["password"])
        self.prices = PvpcPriceAPI(self.api.tz)
        self.currency = hass.config.currency
        self.history_days = entry.options.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS)
        # contractNumber -> contract dict (metadata for the device/sensors)
        self.contracts: dict[str, dict] = {}

    def _compute_cost(self, hourly: list[dict]) -> list[dict]:
        """Multiply each hourly kWh by that hour's PVPC price. Blocking."""
        cost_rows = []
        for row in hourly:
            dt = row["datetime"]
            try:
                price = self.prices.get_day_prices(dt.date()).get(dt.hour)
            except PvpcPriceError as err:
                _LOGGER.warning("Skipping cost for %s: %s", dt.date(), err)
                continue
            if price is None:
                continue
            cost_rows.append({"datetime": dt, "cost": row["kwh"] * price})
        return cost_rows

    def _fetch(self) -> dict:
        """Blocking API access, runs in the executor."""
        contracts = {c["contractNumber"]: c for c in self.api.contracts()}
        consumption = self.api.fetch_consumption(self.history_days)

        costs = {}
        for cid, hourly in consumption.items():
            # CNMC API serves PVPC prices; only meaningful for PVPC contracts.
            if contracts.get(cid, {}).get("specificTariff") == "PVPC":
                costs[cid] = self._compute_cost(hourly)

        return {"contracts": contracts, "consumption": consumption, "costs": costs}

    async def _async_update_data(self):
        try:
            async with asyncio.timeout(90):
                result = await self.hass.async_add_executor_job(self._fetch)
        except InvalidCredentialsError as err:
            raise ConfigEntryAuthFailed from err
        except (IncapsulaDetectedError, EnergiaxxiApiError) as err:
            raise UpdateFailed(str(err)) from err

        self.contracts = result["contracts"]
        consumption = result["consumption"]
        costs = result["costs"]

        for cid, hourly in consumption.items():
            location = contract_location(self.contracts.get(cid, {"contractNumber": cid}))
            await async_import_energy_statistics(
                self.hass, cid, hourly, name=f"Energiaxxi {location} Energy"
            )
            if costs.get(cid):
                await async_import_cost_statistics(
                    self.hass, cid, costs[cid], self.currency,
                    name=f"Energiaxxi {location} Cost",
                )

        return consumption
