# SwissthermScraper

Fetches PZP/Kermi/Grünenwald heat-pump data from the cloud portal and publishes it to MQTT for Home Assistant.

Heizkreis **and** energy counters use the **xcenterpro JSON API** (OpenID login + menu/datapoint endpoints). No Selenium/Chrome is required. MQTT topic names stay compatible with existing Home Assistant entities.

There is still no useful **local** LAN API on a plain x-center x40 (FTP/Telnet only; no HTTP/Modbus without Interface Module).

Overview page the values correspond to:

![grafik](https://user-images.githubusercontent.com/76875781/147733333-31de635b-6b2e-4d15-adb4-5873575ca2ed.png)

## Architecture

| Path | How | When |
|---|---|---|
| Heizkreis / live sensors | `portal_api_client.py` → JSON API | Continuous loop in `app.py` (default every 30 s) |
| Energy counters | `energy.py` → same API (`Menu/GetChildEntries`) | On demand: MQTT `swisstherm/control/zaehler` = `get` |

Counter page UUIDs come from `secrets.portal_datapath_energy` (same URLs as before; only the trailing menu-entry UUID is used).

## MQTT

**Heizkreis** (published each loop):

- `swisstherm/<sensor>` — e.g. `Heizleistung`, `COP`, `Aussentemp.`, `WP-Zustand`, overlay keys (`Vorlauf Ist`, `Mischer`, …)
- `swisstherm/S0-Leistung` — S0 power (human label: Überschuss S0)
- Extra KPI topics: `swisstherm/SCOP`, `swisstherm/COP Hz`, `swisstherm/COP TWE`, `swisstherm/Verdichteraufnahme`

**Control / status** (unchanged):

- `swisstherm/control/delay` — seconds between polls
- `swisstherm/control/waittime` — minutes between reconnect attempts
- `swisstherm/control/retries` — max reconnect attempts
- `swisstherm/control/onoff` — `stop` / `restart`
- `swisstherm/control/zaehler` — `get` triggers energy-counter fetch
- `swisstherm/status` — status text (`Notify: …` forwarded by Home Assistant)
- `swisstherm/zaehler/json` — energy-counter JSON payload

## Home Assistant (MQTT examples)

Minimal `mqtt:` snippets. With a shared `device:`, keep entity `name` / `object_id` **without** a `Swisstherm` prefix — otherwise entity IDs become `sensor.swisstherm_swisstherm_…`. Use `float(default=none)` so bad payloads become `unknown` instead of a fake `0`. Live topics use `expire_after`; Zähler JSON has no expiry (on-demand).

```yaml
mqtt:
  sensor:
  - name: Vorlauf Ist
    unique_id: swisstherm_vorlauf_ist
    state_topic: swisstherm/Vorlauf Ist
    unit_of_measurement: "°C"
    device_class: temperature
    state_class: measurement
    expire_after: 600
    device:  # define once
      identifiers: [swisstherm]
      name: Swisstherm
      manufacturer: PZP / Kermi
      model: x-center

  - name: Gesamtaufnahme Hz
    unique_id: swisstherm_gesamtaufnahme_hz
    state_topic: swisstherm/zaehler/json
    value_template: "{{ value_json['Leistungsaufnahme Hz'] | float(default=none) }}"
    unit_of_measurement: kWh
    device_class: energy
    state_class: total_increasing
    device: 
      identifiers: [swisstherm]
```

## Requires

- Python 3.10+ recommended
- MQTT broker reachable from the host
- Network access to the branded portal (OpenID + `…/xcenterpro/api`)

## Setup

```bash
git clone https://github.com/lindersi/SwissthermScraper.git
cd SwissthermScraper
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp secrets.example.py secrets.py
# edit secrets.py: portal URL/user/password, MQTT host/credentials,
# and portal_datapath_energy URLs (or at least their menu-entry UUIDs)
```

`portal_api_client.py` derives API base, installation id and device id from `portal_loginpath` / `portal_datapath["Heizkreis"]` unless you override the optional fields in `secrets.py`.

## Usage

```bash
python app.py
```

Dry-runs (no MQTT loop):

```bash
python portal_api_client.py once      # Heizkreis dict
python portal_api_client.py energy    # zaehler JSON shape
python portal_api_client.py discover  # datapoint → MQTT mapping
```

- Listen to `swisstherm/#`
- Set interval: publish `30` to `swisstherm/control/delay`
- Set reconnect wait: publish `5` to `swisstherm/control/waittime` (minutes)
- Stop: publish `stop` to `swisstherm/control/onoff`
- Restart session: publish `restart` to `swisstherm/control/onoff`
- Fetch energy counters: publish `get` to `swisstherm/control/zaehler`

## systemd (Linux)

Template: [`swisstherm-scraper.service`](swisstherm-scraper.service).

1. Edit `User`, `Group`, `WorkingDirectory`, and `ExecStart` in the template.
2. Install:

```bash
sudo cp swisstherm-scraper.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now swisstherm-scraper.service
```

- Status: `systemctl status swisstherm-scraper.service`
- Logs: `journalctl -u swisstherm-scraper.service -f`

Do **not** commit a customized unit with real usernames/paths; local copies can live under `unit-files/` (gitignored).

## Layout

- `app.py` — MQTT control loop and Heizkreis poll orchestration
- `portal_api_client.py` — OpenID PKCE + xcenterpro JSON (Heizkreis + energy)
- `energy.py` — on-demand energy counters → `swisstherm/zaehler/json`
- `scrape.py` / `browser.py` / `functions.py` — legacy Selenium helpers (unused by `app.py`)
- `swisstherm-scraper.service` — systemd unit template
- `secrets.py` — local credentials (not in git)
- `playground/` — notes, optional Sheets export, saved HTML for debugging
