import base64
import logging

from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
from functools import cached_property
from collections import defaultdict
from curl_cffi import Session, Curl
from curl_cffi.requests.session import Response

_LOGGER = logging.getLogger(__name__)


class EnergiaxxiApiError(Exception):
    """Generic Energiaxxi API error (unexpected response / parse failure)."""


class InvalidCredentialsError(Exception):
    """Exception raised for invalid username or password."""


class IncapsulaDetectedError(Exception):
    """Exception raised when Incapsula protection is detected."""


class EnergiaxxiAPI:
    def __init__(self, username: str, password: str, tz: ZoneInfo = ZoneInfo("Europe/Madrid")):
        self.username = username
        self.password = password
        self.tz = tz

        self.user_id: str | None = None
        self._authenticated = False
        self.base_url = "https://www.movil.endesaclientes.com/neolapi-ib-es-rest"

        curl = Curl()
        curl.impersonate("chrome")
        self.session = Session(curl)
        self.session.headers = {
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip',
            'Connection': 'close',
            'Content-Type': 'application/json',
            'Host': 'www.movil.endesaclientes.com',
            'Location': 'ib-es-mr',
            'Transfer-Encoding': 'chunked',
            'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 10; Mi A2 Build/QKQ1.190910.002)',
        }

    def _api_request(self, method, path, headers=None, params=None, data=None, json=None, reauthorize=True) -> Response:
        response = self.session.request(
            method=method,
            url=f"{self.base_url}{path}",
            data=data,
            json=json,
            params=params,
            headers=headers,
        )
        if response.status_code == 401 and reauthorize:
            self._refresh_auth()
            response = self.session.request(
                method=method,
                url=f"{self.base_url}{path}",
                data=data,
                json=json,
                params=params,
                headers=headers,
            )
        return response

    def _post(self, path, headers=None, data=None, json=None, reauthorize=True) -> Response:
        return self._api_request("POST", path, headers=headers, data=data, json=json, reauthorize=reauthorize)

    def authenticate(self):
        """Force credential validation. Raises InvalidCredentialsError / IncapsulaDetectedError."""
        self._refresh_auth()

    def _refresh_auth(self):
        body = {"appVersion": "1.5.3", "devicePlatform": "Android"}
        r = self._post("/business/version", json=body, reauthorize=False)

        if r.status_code != 200:
            if "incapsula" in r.text.lower():
                raise IncapsulaDetectedError("Incapsula protection detected, please try again later.")
            raise Exception(f"Failed to get app version: {r.status_code} - {r.text}")

        body = {"password": self.password, "alias": self.username}
        auth = self._post("/business/authentication-v3", json=body, reauthorize=False).json()

        if error := auth.get('errorMessage'):
            if error == "Alias/password incorrect for this resource":
                raise InvalidCredentialsError("Invalid username or password.")
            raise EnergiaxxiApiError(f"Authentication error: {error}")

        if not auth.get('id') or not auth.get('tgt'):
            raise EnergiaxxiApiError(f"Unexpected authentication response: {auth}")

        self.user_id = auth['id']

        auth_token = base64.b64encode(f"{auth['id']}:{auth['tgt']}".encode()).decode()
        self.session.headers["Authorization"] = f"Basic {auth_token}"
        self._authenticated = True

    @cached_property
    def user_info(self):
        body = {"userId": self.user_id}
        user_info = self._post("/users/info-v5", json=body)
        return user_info.json()

    @cached_property
    def contract_info(self):
        body = {"infoRequested": {"rolId": "Titu", "clientId": self.user_info["user"]["clientId"]},
                "userId": self.user_id}
        contract_info = self._post("/users/contractstatessummarized-v3", json=body)
        return contract_info.json()

    def fetch_consumption(self) -> dict:
        """
        Returns dict  contract_number -> [ {date, consumption}, … ]
        """
        if not self._authenticated:
            self._refresh_auth()

        try:
            client_id = self.user_info["user"]["clientId"]
        except (KeyError, TypeError) as err:
            raise EnergiaxxiApiError(f"Unexpected user info response: {self.user_info}") from err

        contracts = self.contract_info.get("contracts")
        if not contracts:
            raise EnergiaxxiApiError(f"No contracts in response: {self.contract_info}")

        now = datetime.now(self.tz)
        consumption = defaultdict(list)
        for contract in contracts:
            body = {
                "contract": {
                    "str": contract["str"],
                    "specificTariff": contract["specificTariff"],
                    "complementHappy": contract["complementHappy"] or "",
                    "isHappy": contract["isHappy"],
                    "contractNumber": contract["contractNumber"],
                    "cups": contract["cups"],
                    "effectiveDate": contract["effectiveDate"],
                    "companyHolderCode": contract["companyHolderCode"],
                },
                "infoRequested": {"rolId": "Titu", "clientId": client_id},
                "periodDetail": {
                    "isCurrentPeriod": True,
                    "invoicedPeriod": {
                        "from": (now - timedelta(days=15)).strftime("%d/%m/%Y"),
                        "to": now.strftime("%d/%m/%Y"),
                    },
                    "billSequence": 0,
                },
                "userId": self.user_id,
            }
            contract_number = contract["contractNumber"]
            r = self._post("/business/contracts/consumptiondetailed-v2", json=body).json()
            _LOGGER.debug("consumptiondetailed response for %s: %s", contract_number, r)

            day_list = (
                (r.get("consumptionDetailed") or {})
                .get("currentYearPeriodDetail", {})
                .get("dayList")
            )
            if not day_list:
                _LOGGER.warning("No consumption data for contract %s", contract_number)
                continue

            for day in day_list:
                for hc in day.get("hourList", []):
                    consum = (hc.get("hourDistribution") or {}).get("consumTotal")
                    if consum is None:
                        continue
                    consumption[contract_number].append(
                        {
                            "datetime": datetime.strptime(
                                f"{day['date']} {hc['hour']}", "%d/%m/%Y %H:%M"
                            ).replace(tzinfo=self.tz),
                            "kwh": float(consum),
                        }
                    )

        for contract_number in consumption:
            consumption[contract_number].sort(key=lambda x: x["datetime"])

        return dict(consumption)
