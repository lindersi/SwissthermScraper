# SwissthermScraper
Scraping swisstherm/grünenwald/kermi/pzp heatpump data from the web portal and publish via MQTT. Uses Python 3, Selenium (Chrome via Selenium Manager), and Paho MQTT.

Currently my only way to get my own data into Home Assistant — no other readable interface found.

Only fits my configuration due to unidentifiable DOM elements (but is easily changeable).

Created with little coding knowledge. Hints for improvement are highly appreciated.

Where data is scraped from:
![grafik](https://user-images.githubusercontent.com/76875781/147733333-31de635b-6b2e-4d15-adb4-5873575ca2ed.png)

## Requires
- Python 3.10+ recommended
- Google Chrome or Chromium installed on the OS
- MQTT broker reachable from the host

No manual chromedriver install is needed: Selenium Manager downloads a matching driver automatically.
Do **not** keep a `chromedriver.exe` in the project folder (or on PATH) — an old binary overrides Selenium Manager and causes version mismatches (the classic Windows/Linux pain point).

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

Optional environment variables:

| Variable | Meaning |
|---|---|
| `STSCRAPER_HEADLESS` | `1`/`true` = headless, `0`/`false` = show browser. Default: headless on Linux, headed on Windows. |
| `STSCRAPER_CHROME_BINARY` | Path to Chrome/Chromium if not on PATH (useful on some Linux installs). |

## Usage
```bash
python app.py
```

- Listen to MQTT topic `swisstherm/#`
- Set interval: publish `30` to `swisstherm/control/delay` (seconds)
- Set reconnect wait: publish `5` to `swisstherm/control/waittime` (minutes)
- Stop: publish `stop` to `swisstherm/control/onoff`
- Restart scrape session: publish `restart` to `swisstherm/control/onoff`
- Fetch energy counters: publish `get` to `swisstherm/control/zaehler`
- Status messages on `swisstherm/status` (payloads starting with `Notify: ` are forwarded by Home Assistant)

## systemd (Linux / server-elitebook)
```
[Unit]
Description=Heatpump-Scraper Service
After=network.target

[Service]
User=YOUR_USERNAME
Group=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/path/to/heatingscraper/
Environment=STSCRAPER_HEADLESS=1
ExecStart=/home/YOUR_USERNAME/path/to/heatingscraper/venv/bin/python /home/YOUR_USERNAME/path/to/heatingscraper/app.py
Restart=always
RestartSec=10s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

## Layout
- `app.py` — MQTT control loop and scrape session orchestration
- `scrape.py` — Heizkreis DOM parsing
- `browser.py` — shared Chrome options / driver lifecycle
- `energy.py` — energy counter scrape (MQTT JSON)
- `functions.py` — portal login helpers
- `gsheet.py` — optional Google Sheets export (dormant)
- `secrets.py` — local credentials (not in git)
