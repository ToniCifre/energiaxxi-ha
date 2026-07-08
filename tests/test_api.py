import pytest

from custom_components.energiaxxi.api import (
    EnergiaxxiApiError,
    IncapsulaDetectedError,
    InvalidCredentialsError,
)
from conftest import CONTRACT, FakeResponse, consumption_response, make_api


def test_constructor_does_no_network(monkeypatch):
    from custom_components.energiaxxi.api import EnergiaxxiAPI
    # Would raise if it tried to POST (no _post patched) — it must not.
    api = EnergiaxxiAPI("u", "p")
    assert api._authenticated is False
    assert api.user_id is None


def test_fetch_consumption_parses_hours(monkeypatch):
    api = make_api(monkeypatch)
    data = api.fetch_consumption(history_days=25)

    assert set(data) == {"130109476822"}
    rows = data["130109476822"]
    assert len(rows) == 24
    assert rows[0]["kwh"] == 0.5
    # sorted, tz-aware, hourly
    assert rows[0]["datetime"] < rows[-1]["datetime"]
    assert rows[0]["datetime"].tzinfo is not None
    assert (rows[1]["datetime"] - rows[0]["datetime"]).seconds == 3600
    assert api._authenticated is True


def test_fetch_sets_basic_auth_header(monkeypatch):
    api = make_api(monkeypatch, auth={"id": "U9", "tgt": "TOK"})
    api.fetch_consumption()
    assert api.user_id == "U9"
    assert api.session.headers["Authorization"].startswith("Basic ")


def test_invalid_credentials(monkeypatch):
    api = make_api(monkeypatch, auth={"errorMessage": "Alias/password incorrect for this resource"})
    with pytest.raises(InvalidCredentialsError):
        api.fetch_consumption()


def test_incapsula_detected(monkeypatch):
    api = make_api(monkeypatch, version_status=403, version_text="... incapsula ...")
    with pytest.raises(IncapsulaDetectedError):
        api.fetch_consumption()


def test_malformed_auth_missing_tgt(monkeypatch):
    api = make_api(monkeypatch, auth={"id": "U1"})  # no tgt
    with pytest.raises(EnergiaxxiApiError):
        api.fetch_consumption()


def test_no_contracts_raises(monkeypatch):
    api = make_api(monkeypatch, contracts={"contracts": []})
    with pytest.raises(EnergiaxxiApiError):
        api.fetch_consumption()


def test_missing_daylist_skips_contract(monkeypatch):
    # consumption response without dayList -> contract skipped, no crash, empty result
    api = make_api(monkeypatch, consumption={"consumptionDetailed": {}})
    assert api.fetch_consumption() == {}


def test_missing_consum_value_is_skipped(monkeypatch):
    resp = consumption_response(n_hours=2)
    # blank one hour's value
    resp["consumptionDetailed"]["currentYearPeriodDetail"]["dayList"][0]["hourList"][1][
        "hourDistribution"
    ]["consumTotal"] = None
    api = make_api(monkeypatch, consumption=resp)
    rows = api.fetch_consumption()["130109476822"]
    assert len(rows) == 1


def test_contracts_helper(monkeypatch):
    api = make_api(monkeypatch)
    contracts = api.contracts()
    assert contracts[0]["cups"] == CONTRACT["cups"]
