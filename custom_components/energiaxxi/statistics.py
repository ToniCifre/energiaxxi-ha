import logging
from datetime import datetime, timezone

from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import EnergyConverter
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    statistics_during_period,
    StatisticMetaData,
    StatisticMeanType,
)

from .const import DOMAIN
from .common import slugify

_LOGGER = logging.getLogger(__name__)

# Lower bound for "all statistics" queries.
_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _row_ts(row) -> float:
    """Return a statistics row's start as an epoch (handles float or datetime)."""
    start = row["start"]
    return start.timestamp() if hasattr(start, "timestamp") else float(start)


def energy_statistic_id(contract_id) -> str:
    return f"{DOMAIN}:energiaxxi_{slugify(str(contract_id))}_energy"


def cost_statistic_id(contract_id) -> str:
    return f"{DOMAIN}:energiaxxi_{slugify(str(contract_id))}_cost"


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

    Reimports the whole batch, anchoring the cumulative sum to the sum of the
    last stored point *before* the batch. This overwrites overlapping rows
    idempotently and, crucially, supports backfilling older data (the running
    sum of a widened window is recomputed from a 0 baseline).
    """
    if not points:
        return

    points = sorted(points, key=lambda p: p[0])
    baseline = await async_get_sum_before(hass, statistic_id, points[0][0])

    _LOGGER.info(
        "Importing %d rows for %s (baseline sum %.2f)", len(points), statistic_id, baseline
    )

    stats = []
    running_sum = baseline
    for dt, value in points:
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


async def async_get_sum_before(hass: HomeAssistant, statistic_id: str, before: datetime) -> float:
    """Sum of the last stored point strictly before `before` (0.0 if none)."""
    rows = await _async_stat_rows(hass, statistic_id, end=before)
    before_ts = before.timestamp()
    prior = [r for r in rows if _row_ts(r) < before_ts]
    if prior and prior[-1].get("sum") is not None:
        return float(prior[-1]["sum"])
    return 0.0


async def async_get_stat_range(hass: HomeAssistant, statistic_id: str):
    """Return (first_start, last_start) as tz-aware UTC datetimes, or (None, None)."""
    rows = await _async_stat_rows(hass, statistic_id, end=dt_util.utcnow())
    if not rows:
        return None, None
    to_dt = lambda r: datetime.fromtimestamp(_row_ts(r), tz=timezone.utc)
    return to_dt(rows[0]), to_dt(rows[-1])


async def _async_stat_rows(hass: HomeAssistant, statistic_id: str, end: datetime):
    stats = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        _EPOCH,
        end,
        {statistic_id},
        "hour",
        None,
        {"sum"},
    )
    return stats.get(statistic_id) or []
