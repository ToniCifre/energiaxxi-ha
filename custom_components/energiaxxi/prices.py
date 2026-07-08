import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from curl_cffi import Curl, Session

_LOGGER = logging.getLogger(__name__)


class PvpcPriceError(Exception):
    """Raised when the CNMC PVPC price API returns an unexpected response."""


class PvpcPriceAPI:
    """Client for the CNMC public PVPC hourly price API."""

    BASE_URL = "https://comparador.cnmc.gob.es/api/publico/preciosPVPC/get"

    def __init__(self, tz: ZoneInfo = ZoneInfo("Europe/Madrid")):
        self.tz = tz
        curl = Curl()
        curl.impersonate("chrome")
        self.session = Session(curl)
        self.session.headers = {
            "accept": "application/json, text/plain, */*",
            "referer": "https://comparador.cnmc.gob.es/preciosPVPC/inicio",
            "user-agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
            ),
        }
        self._cache: dict[date, dict[int, float]] = {}

    def get_day_prices(self, day: date) -> dict[int, float]:
        """Return {hour(0-23) -> price €/kWh} for the given day (cached)."""
        if day in self._cache:
            return self._cache[day]

        ts = int(datetime(day.year, day.month, day.day, tzinfo=self.tz).timestamp() * 1000)
        r = self.session.get(f"{self.BASE_URL}/{ts}-1-1")
        if r.status_code != 200:
            raise PvpcPriceError(f"PVPC price request failed for {day}: {r.status_code}")

        data = r.json()
        prices: dict[int, float] = {}
        for item in data.get("preciosHora", []):
            try:
                hour = int(str(item["hora"])[:2])
                prices[hour] = float(item["precio"])
            except (KeyError, ValueError, TypeError):
                continue

        if not prices:
            raise PvpcPriceError(f"No PVPC prices in response for {day}")

        self._cache[day] = prices
        return prices
