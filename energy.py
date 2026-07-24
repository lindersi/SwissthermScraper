# Sporadic energy-counter scrape; publishes JSON to MQTT (and optionally Google Sheets).

from __future__ import annotations

import datetime
import json
import sys
import time
import traceback

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

import browser
import functions
import secrets

# import gsheet  # optional; enable if Google Sheets export is needed again


def energiezaehler(options, client):
    client.publish("swisstherm/status", payload="Abruf Swisstherm-Zählerstände läuft...")
    print("Abruf Swisstherm-Zählerstände läuft...")

    data = {}
    driver = None

    try:
        driver = browser.create_driver(options)
        functions.login(driver)

        WebDriverWait(driver, 20).until(
            ec.presence_of_element_located((By.CSS_SELECTOR, "main"))
        )

        startfenster = driver.current_window_handle

        for zaehlerwahl in secrets.portal_datapath_energy:
            driver.switch_to.new_window(zaehlerwahl)
            driver.get(secrets.portal_datapath_energy[zaehlerwahl])

            WebDriverWait(driver, 30).until(
                ec.presence_of_element_located((By.CSS_SELECTOR, "div.row-container"))
            )
            time.sleep(2)

            values = driver.find_elements(By.CSS_SELECTOR, "div.row-container > div p")

            if "Wärmemenge" in values[0].text:
                data[values[0].text] = values[1].text.split(" ")[0]
                data[values[2].text] = values[3].text.split(" ")[0]
                data[values[4].text] = values[5].text
                data[values[6].text] = values[7].text.split(" ")[0]
            elif "Betriebsstunden" in values[0].text:
                data[values[0].text] = values[1].text.split(" ")[0]
                data[values[2].text] = values[3].text.split(" ")[0]
                data[values[4].text] = values[5].text.split(" ")[0]
                data[values[6].text] = values[7].text.split(" ")[0]
                data[values[8].text] = values[9].text.split(" ")[0]
                data[values[10].text] = values[11].text.split(" ")[0]
            else:
                raise ValueError(f"Unerwartetes Zähler-Layout: {values[0].text!r}")

            driver.close()
            driver.switch_to.window(startfenster)

        data["Date"] = datetime.datetime.now().strftime("%d.%m.%Y")
        data["Time"] = datetime.datetime.now().strftime("%H:%M:%S")

        client.publish("swisstherm/zaehler/json", payload=json.dumps(data))
        client.publish("swisstherm/status", payload=f"Zähler abgerufen ({len(data)} Werte).")
        print("Swisstherm-Energiezähler erfolgreich abgerufen.")
        client.publish("swisstherm/status", payload="Notify: Swisstherm-Energiezähler erfolgreich abgerufen.")
        # gsheet.main(data, client)

    except Exception as exc:
        print(f"Fehler beim Abruf der Swisstherm-Energiezähler: {exc}")
        print(traceback.format_exc(limit=3))
        client.publish(
            "swisstherm/status",
            payload=f"Notify: Fehler beim Abruf der Swisstherm-Energiezähler: {exc}",
        )
    finally:
        browser.quit_driver(driver)


def write_data(data):
    with open("energy-data.txt", "w", encoding="utf-8") as file:
        file.write(json.dumps(data))
