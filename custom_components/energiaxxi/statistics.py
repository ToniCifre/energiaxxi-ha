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


async def async_import_statistics(hass: HomeAssistant, contract_id, hourly, name=None):
    """
    hourly: list[dict]
        datetime: tz-aware datetime
        kwh     : float
    name: optional human-readable statistic name (falls back to contract id)
    """
    if not hourly:
        return

    statistic_id = f"{DOMAIN}:energiaxxi_{slugify(str(contract_id))}_energy"

    hourly = sorted(hourly, key=lambda x: x["datetime"])

    last_sum, last_start_ts = await async_get_last_stat(hass, statistic_id)

    # Only import rows newer than the last one already stored. This keeps the
    # cumulative sum monotonic across overlapping re-fetches and is robust to
    # arbitrarily long gaps (unlike a fixed lookback window).
    new_rows = [
        row for row in hourly
        if last_start_ts is None or row["datetime"].timestamp() > last_start_ts
    ]
    if not new_rows:
        _LOGGER.debug("No new consumption rows for %s", statistic_id)
        return

    _LOGGER.info(
        "Importing %d rows for %s (previous sum %.2f kWh)",
        len(new_rows), statistic_id, last_sum,
    )

    stats = []
    running_sum = last_sum
    for row in new_rows:
        running_sum += row["kwh"]
        stats.append(
            StatisticData(
                start=row["datetime"],
                state=row["kwh"],
                sum=running_sum,
            )
        )

    metadata = StatisticMetaData(
        name=name or f"Energiaxxi {contract_id} Energy",
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        unit_class=EnergyConverter.UNIT_CLASS,
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
