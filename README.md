# SwissthermScraper
Scraping swisstherm/kermi/pzp heatpump data from the web portal and send through mqqt. Uses Python3, Selenium with Chromium, Paho MQTT.

Only fits my configuration due to unidentifiable DOM elements.

![grafik](https://user-images.githubusercontent.com/76875781/147733333-31de635b-6b2e-4d15-adb4-5873575ca2ed.png)

Usage: 
- Place Python files
- Set web portal domain and user/password
- Set MQQT host
- Change code to extract needed DOM data
- start app.py or use systemd unit file on Linux
- Listen to MQQT topic "swisstherm/#"
- Set intervall with "30" to "swisstherm/delay" (seconds)
- Stop scraping with "stop" to "swisstherm/onoff"
