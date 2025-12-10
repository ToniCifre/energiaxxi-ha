# EnergiaXXI — Custom integration for Home Assistant

This repository contains a simple custom integration for Home Assistant that retrieves energy consumption information from the
[EnergiaXXI](https://www.energiaxxi.com/) electricity supplier.

### Quick summary

- Domain: `energiaxxi`
- Purpose: query hourly consumption and contract-related data linked to an EnergiaXXI account and expose them as sensors
  in Home Assistant.
- Integration: uses a `config_flow` (integration configuration UI) and the `curl-cffi` library to communicate with the
  web API.

### Manual installation

1. Copy the `custom_components/energiaxxi` folder into your Home Assistant `custom_components` directory (usually
   `/config/custom_components/energiaxxi`).
2. Restart Home Assistant.
3. Go to Settings -> Devices & Services -> Add Integration -> Search for "Energiaxxi" and complete the configuration
   flow (username/password).

### What it exposes

Hourly consumption statistics for each contract detected in the account (identified by `contractNumber`). It cannot be created as a sensor because the data reported by EnergiaXXI is a week behind.

You can import the statistics created as a grid consumption in electricity grid.
![electricity_grid.png](images/electricity_grid.png)

### Main component files

- `custom_components/energiaxxi/api.py` — HTTP client that authenticates and fetches detailed consumption data.
- `custom_components/energiaxxi/sensor.py` — Entity (sensor) definitions to expose consumption values.
- `custom_components/energiaxxi/config_flow.py` — Configuration flow for the Home Assistant UI.
- `custom_components/energiaxxi/common.py`, `const.py` — Shared utilities and constants.
- `custom_components/energiaxxi/manifest.json` — Integration metadata and dependencies.

### Important behavior

- The client uses basic authentication built from the user ID and a token (`tgt`) returned by the API.
- If the API returns a response containing the word "incapsula" in an error body, the component raises `IncapsulaDetectedError` (web protection detected).
- If credentials are invalid, the component raises `InvalidCredentialsError`.
