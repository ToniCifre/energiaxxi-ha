import logging
from datetime import datetime, timedelta

from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util.unit_conversion import EnergyConverter
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    StatisticMetaData,
    StatisticMeanType,
    statistics_during_period,
)

from .const import DOMAIN
from .common import slugify

_LOGGER = logging.getLogger(__name__)


async def async_import_statistics(hass: HomeAssistant, contract_id, hourly):
    """
    hourly: list[dict]
        datetime: tz-aware datetime
        kwh     : float
    """
    if not hourly:
        return

    statistic_id = f"{DOMAIN}:energiaxxi_{slugify(str(contract_id))}_energy"

    hourly = sorted(hourly, key=lambda x: x["datetime"])

    last_sum = await async_get_last_sum(hass, hourly[0]["datetime"], statistic_id)
    _LOGGER.info(f"Last sum for {statistic_id} is {last_sum:.2f} kWh")

    stats = []
    running_sum = last_sum
    for row in hourly:
        running_sum += row["kwh"]
        stats.append(
            StatisticData(
                start=row["datetime"],
                state=row["kwh"],
                sum=running_sum,
            )
        )

    metadata = StatisticMetaData(
        name=f"Energiaxxi {contract_id} Energy",
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


async def async_get_last_sum(hass: HomeAssistant, end_time: datetime, statistic_id: str) -> float:
    """Return the last known sum for this statistic within the last 30 days."""
    start_time = end_time - timedelta(days=30)
    stats = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        start_time,
        end_time,
        {statistic_id},
        "hour",
        None,
        {"sum"},
    )
    if stats.get(statistic_id):
        return stats[statistic_id][-1]["sum"]
    return 0.0
