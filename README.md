# SwissthermScraper
Scraping swisstherm/grünenwald/kermi/pzp heatpump data from the web portal and send through mqtt. Uses Python3, Selenium with Chromedriver, Paho MQTT.

Currently my only way to get my own data to use in Homeassistant, because I didn't found any other readable interface.

Only fits my configuration due to unidentifiable DOM elements (but is easily changeable).

Created with little coding knowledge. Hints for improvement are highly appreciated.

Where data is scraped from:
![grafik](https://user-images.githubusercontent.com/76875781/147733333-31de635b-6b2e-4d15-adb4-5873575ca2ed.png)

Requires:
- Python3 environment
- Python modules selenium, paho-mqtt, datetime and sys installed
- Chrome and Chromedriver installed on OS (on Windows, just place chromedriver.exe in the same folder as app.py)

Setup:
- git clone
- python3 -m venv venv
- source venv/bin/activate
- pip install -r requirements.txt
- copy/create secrets.py
- Set web portal domain and user/password 
  (in secrets.py which is for security reasons not part of the repo)
- Set MQTT host and credentials
- Change code to extract needed DOM data (e.g. with the Help of the Chrome Developer Tools)

Usage: 
- start app.py or use systemd unit file on Linux
- Listen to MQTT topic "swisstherm/#"
- Set intervall with "30" to "swisstherm/control/delay" (seconds)
- Set wait time for web reconnection retries with "5" to "swisstherm/control/waittime" (minutes)
- Stop scraping with "stop" to "swisstherm/control/onoff" (stops complete python script)
- Restart with "restart" to "swisstherm/control/onoff"
- Get counters with "get" to "swisstherm/control/zaehler" (total energy consumption, heat production, operating minutes)
- Receive Status on "swisstherm/status"

Info using systemd:
- https://www.dexterindustries.com/howto/run-a-program-on-your-raspberry-pi-at-startup/
- https://www.digitalocean.com/community/tutorials/what-is-systemd

Recommended unit file:
```
[Unit]
Description=Heatpump-Scraper Service
After=network.target

[Service]
User=YOUR_USERNAME
Group=YOUR_USERNAME

WorkingDirectory=/home/YOUR_USERNAME/path/to/heatingscraper/

ExecStart=/home/YOUR_USERNAME/path/to/heatingscraper/venv/bin/python /home/YOUR_USERNAME/path/to/heatingscraper/app.py

Restart=always
RestartSec=10s

StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```
