"""Manual smoke test against the real services (not run by pytest).

Usage:
    ENERGIAXXI_USER=you@example.com ENERGIAXXI_PASS=secret .venv/bin/python manual_test.py
    # or run it without the variables and type the credentials when prompted

What it does:
  1. Logs into EnergiaXXI and prints your contracts and the last days of hourly
     consumption (this is the part that needs your user/password).
  2. Fetches today's and tomorrow's PVPC prices. These come from the public REE
     API and need no credentials, but are the prices EnergiaXXI bills for PVPC.

Set ENERGIAXXI_DEBUG=1 to also log the raw API responses.
"""

import getpass
import logging
import os
from datetime import datetime, timedelta

from custom_components.energiaxxi.api import EnergiaxxiAPI
from custom_components.energiaxxi.prices import PvpcPriceAPI, PvpcPriceError

CONSUMPTION_DAYS = 15


def check_energiaxxi(username: str, password: str) -> None:
    print("== EnergiaXXI")
    api = EnergiaxxiAPI(username, password)

    for contract in api.contracts():
        print(f"Contract {contract['contractNumber']}: tariff={contract.get('specificTariff')}")

    consumption = api.fetch_consumption(CONSUMPTION_DAYS)
    for contract_number, rows in consumption.items():
        total = sum(row["kwh"] for row in rows)
        print(f"\nContract {contract_number}: {len(rows)} hourly rows, {total:.2f} kWh")
        for row in rows[-24:]:
            print(f"  {row['datetime']:%Y-%m-%d %H:%M}  {row['kwh']:.3f} kWh")


def check_prices() -> None:
    print("\n== PVPC prices (REE, €/kWh, no taxes)")
    prices = PvpcPriceAPI()
    today = datetime.now(prices.tz).date()
    for day in (today, today + timedelta(days=1)):
        try:
            by_hour = prices.get_day_prices(day)
        except PvpcPriceError as err:
            print(f"{day}: {err}")
            continue
        cheapest = min(by_hour, key=by_hour.get)
        print(f"{day}: cheapest {cheapest:02d}:00 ({by_hour[cheapest]:.5f})")
        for hour, price in sorted(by_hour.items()):
            print(f"  {hour:02d}:00  {price:.5f}")


def main() -> None:
    logging.basicConfig(
        level=logging.DEBUG if os.environ.get("ENERGIAXXI_DEBUG") else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    username = os.environ.get("ENERGIAXXI_USER") or input("EnergiaXXI user: ")
    password = os.environ.get("ENERGIAXXI_PASS") or getpass.getpass("EnergiaXXI password: ")

    check_energiaxxi(username, password)
    check_prices()


if __name__ == "__main__":
    main()
