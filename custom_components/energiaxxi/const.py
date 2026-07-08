DOMAIN = "energiaxxi"

CONF_HISTORY_DAYS = "history_days"
CONF_PRICE_DAYS = "price_days"
CONF_CONSUMPTION_INTERVAL_HOURS = "consumption_interval_hours"
CONF_PRICE_INTERVAL_HOURS = "price_interval_hours"
# Legacy single-interval option, kept for backward compatibility.
CONF_SCAN_INTERVAL_HOURS = "scan_interval_hours"

DEFAULT_HISTORY_DAYS = 25
DEFAULT_PRICE_DAYS = 7
DEFAULT_CONSUMPTION_INTERVAL_HOURS = 12
DEFAULT_PRICE_INTERVAL_HOURS = 12


def interval_option(options, key: str, default: int) -> int:
    """Read an interval option, falling back to the legacy single interval."""
    return options.get(key, options.get(CONF_SCAN_INTERVAL_HOURS, default))
