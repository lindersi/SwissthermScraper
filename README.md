# SwissthermScraper

Fetches PZP/Kermi/Grünenwald heat-pump data from the cloud portal and publishes it to MQTT for Home Assistant.

**Major change:** Heizkreis values are no longer scraped with Selenium. They come from the same **xcenterpro JSON API** the RemoteControl UI uses (OpenID login + `Menu/GetBundlesByCategory` / `Datapoint/ReadValues`). MQTT topic names stay compatible with existing Home Assistant entities.

There is still no useful **local** LAN API on a plain x-center x40 (FTP/Telnet only; no HTTP/Modbus without Interface Module).

Overview page the values correspond to:

![grafik](https://user-images.githubusercontent.com/76875781/147733333-31de635b-6b2e-4d15-adb4-5873575ca2ed.png)

## Architecture

| Path | How | When |
|---|---|---|
| Heizkreis / live sensors | `portal_api_client.py` → JSON API | Continuous loop in `app.py` (default every 30 s) |
| Energy counters | `energy.py` → Selenium DOM | On demand: MQTT `swisstherm/control/zaehler` = `get` |

Energy counters stay on Selenium for now: they use separate portal counter pages (`portal_datapath_energy`) and a different DOM layout that was **not** mapped onto the JSON API yet. Only Chrome/Chromium is required for that sporadic path.

## MQTT

**Heizkreis** (published each loop):

- `swisstherm/<sensor>` — e.g. `Heizleistung`, `COP`, `Aussentemp.`, `WP-Zustand`, overlay keys (`Vorlauf Ist`, `Mischer`, …)
- `swisstherm_s0_leistung` — flat topic for S0 power (human label: Überschuss S0)
- Extra KPI topics (same naming style): `swisstherm/SCOP`, `swisstherm/COP Hz`, `swisstherm/COP TWE`, `swisstherm/Verdichteraufnahme`

**Control / status** (unchanged):

- `swisstherm/control/delay` — seconds between polls
- `swisstherm/control/waittime` — minutes between reconnect attempts
- `swisstherm/control/retries` — max reconnect attempts
- `swisstherm/control/onoff` — `stop` / `restart`
- `swisstherm/control/zaehler` — `get` triggers energy-counter scrape
- `swisstherm/status` — status text (`Notify: …` forwarded by Home Assistant)
- `swisstherm/zaehler/json` — energy-counter JSON payload

## Requires

- Python 3.10+ recommended
- MQTT broker reachable from the host
- Google Chrome or Chromium — **only** if you use energy-counter fetch (`control/zaehler`)

No manual chromedriver install: Selenium Manager downloads a matching driver.
Do **not** keep a `chromedriver.exe` in the project folder (or on PATH).

## Setup

```bash
git clone https://github.com/lindersi/SwissthermScraper.git
cd SwissthermScraper
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp secrets.example.py secrets.py
# edit secrets.py: portal URL/user/password, MQTT host/credentials
```

`portal_api_client.py` derives API base, installation id and device id from `portal_loginpath` / `portal_datapath["Heizkreis"]` unless you override the optional fields in `secrets.py`.

Optional environment variables (energy-counter / Selenium only):

| Variable | Meaning |
|---|---|
| `STSCRAPER_HEADLESS` | `1`/`true` = headless, `0`/`false` = show browser. Default: headless on Linux, headed on Windows. |
| `STSCRAPER_CHROME_BINARY` | Path to Chrome/Chromium if not on PATH. |

## Usage

```bash
python app.py
```

Dry-run Heizkreis (no MQTT loop):

```bash
python portal_api_client.py once
python portal_api_client.py discover   # dump portal datapoint → MQTT mapping
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
- `portal_api_client.py` — OpenID PKCE + xcenterpro JSON → Heizkreis MQTT keys
- `energy.py` — energy-counter Selenium scrape → `swisstherm/zaehler/json`
- `browser.py` / `functions.py` — Chrome + portal login helpers (energy path)
- `scrape.py` — legacy Heizkreis DOM parser (unused by `app.py`)
- `swisstherm-scraper.service` — systemd unit template
- `secrets.py` — local credentials (not in git)
- `playground/` — notes, optional Sheets export, saved HTML for debugging
