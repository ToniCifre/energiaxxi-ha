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

    def fake_sdp(hass, start, end, ids, period, units, types):
        sid = next(iter(ids))
        rows = [
            r for r in table
            if r["sid"] == sid and r["start"].timestamp() < end.timestamp()
        ]
        rows.sort(key=lambda r: r["start"])
        return {sid: [{"start": r["start"].timestamp(), "sum": r["sum"]} for r in rows]}

    def fake_add(hass, metadata, stats):
        sid = metadata["statistic_id"]
        for s in stats:
            # upsert by (sid, start), like the recorder
            table[:] = [
                r for r in table if not (r["sid"] == sid and r["start"] == s["start"])
            ]
            table.append({"sid": sid, "start": s["start"], "sum": s.get("sum"),
                          "state": s.get("state"), "mean": s.get("mean")})
        table.sort(key=lambda r: (r["sid"], r["start"]))
        capture["metadata"] = metadata
        capture["n"] = len(stats)

    monkeypatch.setattr(st, "get_instance", lambda hass: _FakeInstance())
    monkeypatch.setattr(st, "statistics_during_period", fake_sdp)
    monkeypatch.setattr(st, "async_add_external_statistics", fake_add)
    return table, capture


def _sids(table, sid):
    return [r for r in table if r["sid"] == sid]


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


def test_backfill_older_days_are_inserted(monkeypatch):
    # regression: widening the window must insert older days (previously skipped)
    table, _ = _install_fake_recorder(monkeypatch)
    imp = st.async_import_energy_statistics

    asyncio.run(imp(None, "C", _rows(25, 24, 0.5)))            # only day25 stored first
    assert len(table) == 24

    # now a wider window arrives: day24 (older!) + day25
    asyncio.run(imp(None, "C", _rows(24, 24, 1.0) + _rows(25, 24, 0.5)))

    assert len(table) == 48                        # day24 backfilled
    starts = [r["start"] for r in table]
    assert min(starts) == datetime(2026, 6, 24, 0, 0, tzinfo=TZ)
    sums = [r["sum"] for r in table]
    assert sums == sorted(sums)                    # recomputed from a 0 baseline
    assert table[0]["sum"] == 1.0                  # day24 hour0 = 1.0, baseline 0


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
