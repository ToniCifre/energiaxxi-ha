import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from curl_cffi import Curl, Session

_LOGGER = logging.getLogger(__name__)


class PvpcPriceError(Exception):
    """Raised when the REE PVPC price API returns an unexpected response."""


class PvpcPriceAPI:
    """Client for the public REE (Red Eléctrica) PVPC hourly price API."""

    BASE_URL = "https://apidatos.ree.es/es/datos/mercados/precios-mercados-tiempo-real"
    # Peninsular system (geo_ids 8741); the PVPC indicator in the response has id "1001".
    GEO_PARAMS = "geo_limit=peninsular&geo_ids=8741"
    PVPC_ID = "1001"

    def __init__(self, tz: ZoneInfo = ZoneInfo("Europe/Madrid")):
        self.tz = tz
        curl = Curl()
        curl.impersonate("chrome")
        self.session = Session(curl)
        self.session.headers = {"accept": "application/json"}
        self._cache: dict[date, dict[int, float]] = {}

    def get_day_prices(self, day: date) -> dict[int, float]:
        """Return {hour(0-23) -> price €/kWh} for the given day (cached)."""
        if day in self._cache:
            return self._cache[day]

        d = day.isoformat()
        url = (
            f"{self.BASE_URL}?start_date={d}T00:00&end_date={d}T23:59"
            f"&time_trunc=hour&{self.GEO_PARAMS}"
        )
        r = self.session.get(url)
        if r.status_code != 200:
            raise PvpcPriceError(f"PVPC price request failed for {day}: {r.status_code}")

        data = r.json()
        values = next(
            (
                inc.get("attributes", {}).get("values", [])
                for inc in data.get("included", [])
                if inc.get("id") == self.PVPC_ID or inc.get("type") == "PVPC"
            ),
            [],
        )
        prices: dict[int, float] = {}
        for item in values:
            try:
                dt = datetime.fromisoformat(item["datetime"]).astimezone(self.tz)
                if dt.date() != day:
                    continue
                # REE reports €/MWh; the integration works in €/kWh.
                prices.setdefault(dt.hour, float(item["value"]) / 1000)
            except (KeyError, ValueError, TypeError):
                continue

        if not prices:
            raise PvpcPriceError(f"No PVPC prices in response for {day}")

        self._cache[day] = prices
        return prices
