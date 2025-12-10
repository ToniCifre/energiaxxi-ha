import base64

from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
from functools import cached_property
from collections import defaultdict
from curl_cffi import Session, Curl
from curl_cffi.requests.session import Response


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

        self._refresh_auth()

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
            raise Exception(f"Authentication error: {error}")

        self.user_id = auth['id']

        auth_token = base64.b64encode(f"{auth['id']}:{auth['tgt']}".encode()).decode()
        self.session.headers["Authorization"] = f"Basic {auth_token}"

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
        consumption = defaultdict(list)
        for contract in self.contract_info["contracts"]:
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
                "infoRequested": {"rolId": "Titu", "clientId": self.user_info["user"]["clientId"]},
                "periodDetail": {
                    "isCurrentPeriod": True,
                    "invoicedPeriod": {
                        "from": (datetime.now() - timedelta(days=15)).strftime("%d/%m/%Y"),
                        "to": datetime.now().strftime("%d/%m/%Y"),
                    },
                    "billSequence": 0,
                },
                "userId": self.user_id,
            }
            r = self._post("/business/contracts/consumptiondetailed-v2", json=body).json()
            print(r)

            for day in r["consumptionDetailed"]["currentYearPeriodDetail"]["dayList"]:
                for hc in day["hourList"]:
                    consumption[contract["contractNumber"]].append(
                        {
                            "datetime": datetime.strptime(
                                f"{day['date']} {hc['hour']}", "%d/%m/%Y %H:%M"
                            ).replace(tzinfo=self.tz),
                            "kwh": float(hc["hourDistribution"]["consumTotal"]),
                        }
                    )

        for contract_number in consumption:
            consumption[contract_number].sort(key=lambda x: x["datetime"])

        return dict(consumption)
