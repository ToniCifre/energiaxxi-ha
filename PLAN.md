# PLAN — Energiaxxi mejoras

## Contexto

Integración statistics-only para consumo eléctrico Energiaxxi (Endesa). Ya funciona:
importa estadística horaria externa por contrato y se selecciona en el Energy
dashboard. Este plan añade robustez y UX. El **cost tracking (#1)** lo implementa
el usuario por separado (requiere mapear campos de precio de la respuesta API).

Hallazgos de sondeo a la API real:
- Ventana de 15 días con `isCurrentPeriod:True` devuelve datos (parcial, con ~9 días
  de lag de Endesa). Ventanas >30d y `billSequence` de facturas pasadas devuelven
  vacío → **la API limita al periodo de facturación actual**. Backfill largo NO es
  posible con este endpoint; `history_days` se hace configurable pero acotado.
- Campos de contrato útiles: `cups`, `physicalAddress` (calle/nº/ciudad), `specificTariff`
  (p.ej. PVPC), `rate` (2.0TD), `power` (kW), `status`.

## Alcance

Implementar: #2 backfill (configurable), #3 fix suma, y UX #4/#5/#6.

---

### #3 — Fix `async_get_last_sum` (statistics.py)

**Problema:** usa `statistics_during_period` con ventana de 30 días. Si HA está parado
>30 días, devuelve `0.0` → la suma acumulada se resetea → salto/pico falso en el
Energy dashboard.

**Fix:** usar `get_last_statistics(hass, 1, statistic_id, True, {"sum"})` → devuelve el
último punto sin límite temporal. Robusto ante huecos largos.

### #2 — Ventana histórica configurable (api.py + coordinator.py)

- `fetch_consumption(history_days: int)` parametriza el rango `invoicedPeriod`.
- Coordinator lee `history_days` de las opciones (default `DEFAULT_HISTORY_DAYS = 25`).
- Documentar en strings que Endesa limita al periodo actual; valores altos pueden no
  traer más datos.

### #5 — Options flow (config_flow.py + const.py + traducciones)

`OptionsFlow` con:
- `history_days` (int, default 25)
- `scan_interval_hours` (int, default 12)

`__init__.py` registra un update-listener que recarga la entrada al cambiar opciones.
Coordinator usa `scan_interval_hours` para `update_interval`.

### #6 — Nombres legibles (statistics.py + coordinator.py)

- Construir nombre amigable desde `physicalAddress` (calle nº, ciudad) con fallback a
  `contractNumber`. Ej.: `Energiaxxi LLEVANT 22 (Port de Pollença) Energy`.
- **NO cambiar `statistic_id`** (rompería el histórico existente). Solo el campo `name`
  de la metadata.

### #4 — Device registry + sensor diagnóstico (nuevo sensor.py + platform wiring)

External statistics no cuelgan de un device (necesitan entidad). Para dar UX de device
(renombrar, área, agrupar) se añade un sensor diagnóstico por contrato:

- `EnergiaxxiLastReadingSensor`: `device_class=timestamp`, `entity_category=diagnostic`,
  estado = último `datetime` importado del contrato.
- `DeviceInfo`: `identifiers={(DOMAIN, cups)}`, nombre = dirección, `manufacturer="Endesa"`,
  `model=rate` (2.0TD), `serial_number=cups`.
- El sensor NO es la fuente de energía (sigue siendo la external statistic); solo ancla
  el device y expone metadatos del contrato como atributos.

Requiere:
- `PLATFORMS = [Platform.SENSOR]` en `__init__.py` + `async_forward_entry_setups` /
  `async_unload_platforms`.
- Coordinator expone metadatos de contratos (`api.contract_info["contracts"]`).

---

## Ficheros

- `const.py` — claves de opciones + defaults
- `api.py` — `fetch_consumption(history_days)`
- `statistics.py` — `get_last_statistics` (#3), parámetro `name` (#6)
- `coordinator.py` — opciones, scan interval, naming, metadatos de contrato, forward platform
- `__init__.py` — PLATFORMS forward/unload + options update listener
- `config_flow.py` — `OptionsFlow`
- `sensor.py` (nuevo) — sensor diagnóstico + DeviceInfo
- `strings.json` + `translations/{en,es}.json` — textos options flow

## Verificación

1. `python -m py_compile` de todos los módulos + import contra HA instalado.
2. Ejecutar sondeo API (`tests/`) confirmando que `fetch_consumption(history_days=25)`
   devuelve datos con misma forma (144-pt/día horario).
3. Validar offline la lógica `get_last_statistics` (mock) — suma continúa, no resetea.
4. Deploy vía scp + reinicio HA: comprobar device creado (Settings → Devices), sensor
   diagnóstico con timestamp, y que la estadística sigue en el Energy picker.
