# Climate Circuits

Home Assistant integrácia, ktorá určuje režim domu (kúrenie / chladenie / vypnuté) a riadi okruhy kúrenia a chladenia: požiadavku zo zón, čerpadlo, zmiešavač a cieľovú teplotu vody podľa ekvitermickej krivky.

Všetko sa nastavuje v UI. Architektúra, rozhodnutia a plán sú v [documents/](documents/README.md).

## Stav

Míľnik 1 – **iba sleduje, nič neovláda**:

- režim domu zo zdroja (climate, select, sensor, switch) so zálohou podľa nádrže alebo vonkajšej teploty a ručným prepínačom,
- pre každý okruh požiadavka zo zón a cieľová teplota vody (krivka kúrenia / chladenia, pri chladení nikdy pod rosný bod + 2 K),
- prepínač `Control equipment` a senzor stavu (zatiaľ vždy skúšobný režim, výstupy pribudnú v míľniku 2).

## Entity

| Entita | Účel |
|---|---|
| `sensor.climate_circuits_mode` | režim, atribúty `source`, `reason` |
| `select.climate_circuits_mode_override` | auto / heat / cool / off |
| `sensor.climate_circuits_status` | dry_run / ok |
| `switch.climate_circuits_control_equipment` | ostrý režim (zatiaľ bez výstupov) |
| `binary_sensor.<okruh>_demand` | požiadavka, atribúty `zones`, `reason` |
| `sensor.<okruh>_target_water_temperature` | cieľ vody, atribúty `reason`, `dew_point` |

## Vývoj

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv -r requirements-dev.txt
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```
