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


def test_fetch_consumption_dedupes_across_batches(monkeypatch):
    # 40-day history -> 3 batches, all returning the same canned day -> dedup to 24h
    api = make_api(monkeypatch)
    rows = api.fetch_consumption(history_days=40)["130109476822"]
    assert len(rows) == 24
    assert len({r["datetime"] for r in rows}) == 24


class TestDateBatches:
    def _run(self, days, size=15):
        from datetime import date, timedelta
        from custom_components.energiaxxi.api import _date_batches
        start = date(2026, 1, 1)
        end = start + timedelta(days=days)
        return start, end, _date_batches(start, end, size)

    def test_single_batch_when_within_size(self):
        start, end, batches = self._run(10)
        assert batches == [(start, end)]

    def test_multiple_batches_have_size_span(self):
        from datetime import timedelta
        _, _, batches = self._run(40, size=15)
        assert len(batches) == 3  # [0-15], [15-30], [30-40]
        for frm, to in batches:
            assert (to - frm).days <= 15

    def test_batches_are_contiguous_and_cover_range(self):
        start, end, batches = self._run(40, size=15)
        assert batches[0][0] == start
        assert batches[-1][1] == end
        # consecutive windows share the boundary day (overlap for safe coverage)
        for (a, b), (c, d) in zip(batches, batches[1:]):
            assert b == c

    def test_exact_multiple(self):
        start, end, batches = self._run(30, size=15)
        assert batches[0] == (start, start.replace(day=16))
        assert batches[-1][1] == end
