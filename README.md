# SwissthermScraper
Scraping swisstherm/kermi/pzp heatpump data from the web portal and send through mqqt. Uses Python3, Selenium with Chromium, Paho MQTT.

Only fits my configuration due to unidentifiable DOM elements.

![grafik](https://user-images.githubusercontent.com/76875781/147733333-31de635b-6b2e-4d15-adb4-5873575ca2ed.png)

Usage: 
- Place Python files
- Set web portal domain and user/password 
  (in secrets.py which is for security reasons not part of the repo)
- Set MQTT host
- Change code to extract needed DOM data
- start app.py or use systemd unit file on Linux
- Listen to MQTT topic "swisstherm/#"
- Set intervall with "30" to "swisstherm/delay" (seconds)
- Stop scraping with "stop" to "swisstherm/onoff" (no restart possible via mqtt)
- Receive Status on "swisstherm/status" (only start and errors)

Info using systemd:
- https://www.dexterindustries.com/howto/run-a-program-on-your-raspberry-pi-at-startup/
- https://www.digitalocean.com/community/tutorials/what-is-systemd

Recommended unit file:
```
[Unit]
Description=Swisstherm-Scraper
Wants=network-online.target
After=network-online.target

[Service]
Type=idle
ExecStart=/usr/bin/python /home/pi/python-projects/SwissthermScraper/app.py  > /home/pi/swisstherm.log

[Install]
WantedBy=multi-user.target
```
