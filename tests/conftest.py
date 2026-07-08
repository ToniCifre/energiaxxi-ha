import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeResponse:
    """Minimal stand-in for a curl_cffi Response."""

    def __init__(self, payload=None, status_code=200, text=None):
        self._payload = payload
        self.status_code = status_code
        self.text = text if text is not None else (
            json.dumps(payload) if payload is not None else ""
        )

    def json(self):
        return self._payload


# A representative contract as returned by contractstatessummarized-v3.
CONTRACT = {
    "str": "S",
    "specificTariff": "PVPC",
    "complementHappy": None,
    "isHappy": False,
    "contractNumber": "130109476822",
    "cups": "ES0031500232889001BR0F",
    "effectiveDate": "07/10/2024",
    "companyHolderCode": "70",
    "rate": "2.0TD",
    "power": 5.75,
    "physicalAddress": {
        "street": "LLEVANT",
        "number": "22",
        "descriptionMunicipaly": "POLLENÇA",
        "descriptionCity": "PORT DE POLLENÇA",
    },
}


def consumption_response(date="24/06/2026", n_hours=24, kwh="0.5"):
    hours = [
        {"hour": f"{h:02d}:00", "hourDistribution": {"consumTotal": kwh}}
        for h in range(n_hours)
    ]
    return {
        "consumptionDetailed": {
            "currentYearPeriodDetail": {"dayList": [{"date": date, "hourList": hours}]}
        }
    }


def price_response(base=0.20):
    return {
        "preciosHora": [
            {"hora": f"{h:02d}-{h+1:02d}h", "precio": round(base + h * 0.001, 6), "clase": "verde"}
            for h in range(24)
        ]
    }


def make_api(monkeypatch, *, auth=None, user=None, contracts=None, consumption=None,
             version_status=200, version_text=""):
    """Build an EnergiaxxiAPI whose _post is routed to canned responses (no network)."""
    from custom_components.energiaxxi.api import EnergiaxxiAPI

    auth = auth if auth is not None else {"id": "U1", "tgt": "T1"}
    user = user if user is not None else {"user": {"clientId": "C1"}}
    contracts = contracts if contracts is not None else {"contracts": [dict(CONTRACT)]}
    consumption = consumption if consumption is not None else consumption_response()

    routes = {
        "/business/version": FakeResponse({}, version_status, version_text),
        "/business/authentication-v3": FakeResponse(auth),
        "/users/info-v5": FakeResponse(user),
        "/users/contractstatessummarized-v3": FakeResponse(contracts),
        "/business/contracts/consumptiondetailed-v2": FakeResponse(consumption),
    }

    api = EnergiaxxiAPI("user@example.com", "secret")

    def fake_post(path, headers=None, data=None, json=None, reauthorize=True):
        return routes[path]

    monkeypatch.setattr(api, "_post", fake_post)
    return api
