import logging

from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util.unit_conversion import EnergyConverter
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    StatisticMetaData,
    StatisticMeanType,
)

from .const import DOMAIN
from .common import slugify

_LOGGER = logging.getLogger(__name__)


def energy_statistic_id(contract_id) -> str:
    return f"{DOMAIN}:energiaxxi_{slugify(str(contract_id))}_energy"


def cost_statistic_id(contract_id) -> str:
    return f"{DOMAIN}:energiaxxi_{slugify(str(contract_id))}_cost"


def price_statistic_id() -> str:
    return f"{DOMAIN}:pvpc_price"


async def async_import_price_statistics(hass: HomeAssistant, points, currency, name=None):
    """Import hourly PVPC price as a mean statistic. points: list[(datetime, price)].

    Prices are national (not per contract) and known day-ahead, so this is a plain
    mean statistic with no cumulative sum; re-importing overwrites by timestamp.
    """
    if not points:
        return

    points = sorted(points, key=lambda p: p[0])
    stats = [StatisticData(start=dt, mean=price) for dt, price in points]

    metadata = StatisticMetaData(
        name=name or "Energiaxxi PVPC Price",
        source=DOMAIN,
        statistic_id=price_statistic_id(),
        unit_of_measurement=f"{currency}/kWh",
        unit_class=None,
        has_sum=False,
        mean_type=StatisticMeanType.ARITHMETIC,
    )
    await get_instance(hass).async_add_executor_job(
        async_add_external_statistics, hass, metadata, stats
    )


async def async_import_energy_statistics(hass: HomeAssistant, contract_id, hourly, name=None):
    """Import hourly energy (kWh). hourly: list[{datetime, kwh}]."""
    points = [(row["datetime"], row["kwh"]) for row in hourly]
    await _async_import(
        hass,
        energy_statistic_id(contract_id),
        name or f"Energiaxxi {contract_id} Energy",
        UnitOfEnergy.KILO_WATT_HOUR,
        EnergyConverter.UNIT_CLASS,
        points,
    )


async def async_import_cost_statistics(hass: HomeAssistant, contract_id, hourly, currency, name=None):
    """Import hourly cost. hourly: list[{datetime, cost}]. currency e.g. 'EUR'."""
    points = [(row["datetime"], row["cost"]) for row in hourly]
    await _async_import(
        hass,
        cost_statistic_id(contract_id),
        name or f"Energiaxxi {contract_id} Cost",
        currency,
        None,
        points,
    )


async def _async_import(hass, statistic_id, name, unit, unit_class, points):
    """
    points: list[(tz-aware datetime, float value)]
    Accumulates a monotonic sum, skipping points already stored.
    """
    if not points:
        return

    points = sorted(points, key=lambda p: p[0])

    last_sum, last_start_ts = await async_get_last_stat(hass, statistic_id)

    # Only import points newer than the last stored one. Keeps the cumulative
    # sum monotonic across overlapping re-fetches and is robust to long gaps.
    new_points = [
        (dt, value) for dt, value in points
        if last_start_ts is None or dt.timestamp() > last_start_ts
    ]
    if not new_points:
        _LOGGER.debug("No new rows for %s", statistic_id)
        return

    _LOGGER.info(
        "Importing %d rows for %s (previous sum %.2f)",
        len(new_points), statistic_id, last_sum,
    )

    stats = []
    running_sum = last_sum
    for dt, value in new_points:
        running_sum += value
        stats.append(StatisticData(start=dt, state=value, sum=running_sum))

    metadata = StatisticMetaData(
        name=name,
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=unit,
        unit_class=unit_class,
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
    )
    await get_instance(hass).async_add_executor_job(
        async_add_external_statistics, hass, metadata, stats
    )


async def async_get_last_stat(hass: HomeAssistant, statistic_id: str) -> tuple[float, float | None]:
    """Return (last sum, last start epoch) for this statistic, regardless of age."""
    stats = await get_instance(hass).async_add_executor_job(
        get_last_statistics,
        hass,
        1,
        statistic_id,
        True,
        {"sum"},
    )
    if stats.get(statistic_id):
        row = stats[statistic_id][0]
        return float(row["sum"] or 0.0), row.get("start")
    return 0.0, None
