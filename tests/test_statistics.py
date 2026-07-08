import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import custom_components.energiaxxi.statistics as st

TZ = ZoneInfo("Europe/Madrid")


class _FakeInstance:
    async def async_add_executor_job(self, fn, *args):
        return fn(*args)


def _install_fake_recorder(monkeypatch):
    """Patch recorder access; return the in-memory statistics table + capture dict."""
    table = []
    capture = {}

    def fake_get_last(hass, n, sid, convert, types):
        rows = [r for r in table if r["sid"] == sid]
        if not rows:
            return {}
        last = rows[-1]
        return {sid: [{"sum": last["sum"], "start": last["start"].timestamp()}]}

    def fake_add(hass, metadata, stats):
        for s in stats:
            table.append({"sid": metadata["statistic_id"], "start": s["start"],
                          "sum": s["sum"], "state": s["state"]})
        capture["metadata"] = metadata
        capture["n"] = len(stats)

    monkeypatch.setattr(st, "get_instance", lambda hass: _FakeInstance())
    monkeypatch.setattr(st, "get_last_statistics", fake_get_last)
    monkeypatch.setattr(st, "async_add_external_statistics", fake_add)
    return table, capture


def _rows(day, hours, kwh=0.5):
    base = datetime(2026, 6, day, 0, 0, tzinfo=TZ)
    return [{"datetime": base + timedelta(hours=i), "kwh": kwh} for i in range(hours)]


def test_energy_metadata_and_sum(monkeypatch):
    table, cap = _install_fake_recorder(monkeypatch)
    asyncio.run(st.async_import_energy_statistics(None, "130109476822", _rows(24, 24, 0.5), name="E"))

    md = cap["metadata"]
    assert md["statistic_id"] == "energiaxxi:energiaxxi_130109476822_energy"
    assert md["unit_of_measurement"] == "kWh"
    assert md["unit_class"] == "energy"
    assert md["has_sum"] is True
    assert md["name"] == "E"
    assert table[-1]["sum"] == 12.0  # 24 * 0.5


def test_overlapping_refetch_does_not_double_count(monkeypatch):
    table, _ = _install_fake_recorder(monkeypatch)
    imp = st.async_import_energy_statistics

    asyncio.run(imp(None, "C", _rows(24, 24, 0.5)))            # day24
    asyncio.run(imp(None, "C", _rows(24, 24, 0.5) + _rows(25, 24, 1.0)))  # overlap + day25
    asyncio.run(imp(None, "C", _rows(24, 24, 0.5)))            # fully overlapping

    assert len(table) == 48                 # only 24 + 24 new rows stored
    assert table[-1]["sum"] == 36.0         # 12 + 24*1.0, no double count
    sums = [r["sum"] for r in table]
    assert sums == sorted(sums)             # monotonic


def test_empty_input_noop(monkeypatch):
    table, _ = _install_fake_recorder(monkeypatch)
    asyncio.run(st.async_import_energy_statistics(None, "C", []))
    assert table == []


def test_cost_statistic(monkeypatch):
    table, cap = _install_fake_recorder(monkeypatch)
    base = datetime(2026, 6, 24, 0, 0, tzinfo=TZ)
    cost_rows = [{"datetime": base + timedelta(hours=i), "cost": 0.1} for i in range(24)]
    asyncio.run(st.async_import_cost_statistics(None, "130109476822", cost_rows, "EUR", name="C"))

    md = cap["metadata"]
    assert md["statistic_id"] == "energiaxxi:energiaxxi_130109476822_cost"
    assert md["unit_of_measurement"] == "EUR"
    assert md["unit_class"] is None
    assert round(table[-1]["sum"], 4) == 2.4  # 24 * 0.1


def test_statistic_id_helpers():
    assert st.energy_statistic_id("A B") == "energiaxxi:energiaxxi_a_b_energy"
    assert st.cost_statistic_id("A B") == "energiaxxi:energiaxxi_a_b_cost"
